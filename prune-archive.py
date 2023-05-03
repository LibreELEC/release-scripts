#!/usr/bin/env python

# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2016-present Team LibreELEC (https://libreelec.tv)

# requires python >= 3.8

import argparse
import os
import re
import sys
from datetime import datetime, timedelta


DISTRO_NAME='LibreELEC'


class ManageArchive():
    def lchop(self, s, prefix):
        """Remove prefix from string."""
        if prefix and s.startswith(prefix):
            return s[len(prefix):]
        return s


    def rchop(self, s, suffix):
        """Remove suffix from string."""
        if suffix and s.endswith(suffix):
            return s[:-len(suffix)]
        return s


    def __init__(self, args):
        self._indir = self.rchop(args.input, os.path.sep)

        if not os.path.exists(self._indir):
            raise Exception(f'ERROR: invalid path: {self._indir}')

        # nightly image format: {distro}-{proj.device}-{train}-nightly-{date}-githash{-uboot}(.img.gz || .tar)
        self._regex_nightly_image = re.compile(r'''
            ^(\w+)                   # Distro (alphanumerics)
            -([0-9a-zA-Z_-]+[.]\w+)  # Device (alphanumerics+'-'.alphanumerics)
            -(\d+[.]\d+)             # Train (decimals.decimals)
            -nightly-(\d+)           # Date (decimals)
            -([0-9a-fA-F]+)          # Git Hash (hexadecimals)
            (\S*)                    # Uboot name with leading '-' (non-whitespace)
            \.img\.gz''', re.VERBOSE)


    def __enter__(self):
        return self


    def __exit__(self, type, value, traceback):
        pass


    def PruneArchive(self):
        path = self._indir
        retention = int(args.keep)

        # Walk input directory, selecting files for subsequent processing.
        # Search for 'LibreELEC-.*.img.gz' files.
        list_of_files = []
        builds = []
        for (dirpath, dirnames, filenames) in os.walk(path):
            for f in filenames:
                if f.startswith(f'{DISTRO_NAME}-'):
                    # nightly images
                    if f.endswith('.img.gz') and 'nightly' in f:
                        try:
                            parsed_fname = self._regex_nightly_image.search(f)
                        except Exception:
                            print(f'Failed to parse filename: {f}')
                            continue
                    else:
                        if args.verbose:
                            print(f'Ignored file: {f}')
                        continue

#                    fname_parsed = parsed_fname.group(0)
                    fname_distro = parsed_fname.group(1)
                    fname_device = parsed_fname.group(2)
#                    fname_train = parsed_fname.group(3)
                    fname_date = parsed_fname.group(4)
#                    fname_githash = parsed_fname.group(5)
                    fname_uboot = self.lchop(parsed_fname.group(6), '-') if parsed_fname.group(6) else None
#                    fname_timestamp = datetime.fromtimestamp(os.path.getmtime(os.path.join(dirpath,f))).isoformat(sep=' ', timespec='seconds')

                    if fname_device not in builds:
#                        if args.verbose:
#                            print(f'Adding to builds: {fname_device}')
                        builds.append(fname_device)

#                    list_of_files.append([f, fname_device, fname_date, fname_githash, fname_uboot, dirpath, fname_timestamp])
                    list_of_files.append([f, fname_device, fname_date, fname_uboot, dirpath])
                else:
                    if args.verbose:
                        print(f'Ignored file: {f}')
                    continue

        # Sort file list by date in filename
        list_of_files.sort(key=lambda data: data[2])

        # Sort list of builds (eg. RPi2.arm, Generic.x86_64 etc.)
        builds = sorted(builds)
        if args.verbose:
            print(builds)


        # determine files to delete
        kept_filepaths = []
        purge_filepaths = []
        kept_filesize = 0
        purge_filesize = 0
        purge_date = datetime.now() - timedelta(days=retention)

        for build in builds: # ex: RPi2.arm
            release_weeks = []
            for release_file in list_of_files:
                # process one build at a time
                if build in release_file:
                    file_date = release_file[2]
                    file_device = release_file[3] if release_file[3] else build
                    # convert YYYYMMDD date string to iso format, then to a datetime object
                    file_datetime = datetime.fromisoformat(f'{file_date[0:4]}-{file_date[4:6]}-{file_date[6:8]}')
                    if file_datetime < purge_date:
                        file_fullpath = f'{release_file[4]}/{release_file[0]}'
                        file_size = os.path.getsize(file_fullpath)
                        # get year and week from datetime object
                        file_year = file_datetime.isocalendar()[0]
                        file_week = file_datetime.isocalendar()[1]
                        file_details = [file_fullpath, file_date, file_size, f'{file_year}-{file_week}']
                        # if year-week not there, add year-week to list
                        if f'{file_device};{file_year}-{file_week}' not in release_weeks:
                            release_weeks.append(f'{file_device};{file_year}-{file_week}')
                            kept_filesize += file_size
                            kept_filepaths.append(file_details)
                        # else add path/filename to list of files to delete
                        else:
                            purge_filesize += file_size
                            purge_filepaths.append(file_details)
        # sort files for processing based on their date
        kept_filepaths.sort(key=lambda data: data[1])
        purge_filepaths.sort(key=lambda data: data[1])


        # list files to keep - does not include files within RETENTION
        if kept_filepaths:
            if args.verbose or args.retained:
                print('Below files selected for keeping:')
                for f in kept_filepaths:
                    file_name = f[0].split(os.path.sep)[-1]
                    file_size = f[2]
                    file_week = f[3]
                    if args.verbose:
                        print(f'{file_name}\t{file_size}\t{file_week}')
                    elif args.retained:
                        print(f[0])
                if args.verbose:
                    print(f'Total size of kept files: {kept_filesize/(1024**2)}MiB')
            if args.retained:
                sys.exit()
        # list files to delete
        if purge_filepaths:
            if args.verbose:
                print('\nBelow files selected for purging:')
                if not args.delete:
                    print('  --delete not invoked. Keeping all files.')
            for f in purge_filepaths:
                if args.verbose:
                    file_name = f[0].split(os.path.sep)[-1]
                    file_size = f[2]
                    file_week = f[3]
                    print(f'{file_name}\t{file_size}\t{file_week}')
                else:
                    print(f[0])
                # delete if requested
                if args.delete and os.path.isfile(f[0]):
                    os.remove(f[0])
            if args.verbose:
                print(f'Total size of purged files: {purge_filesize/(1024**2)}MiB')
        else:
            print('Nothing found to delete.')


parser = argparse.ArgumentParser(description=f'Prune {DISTRO_NAME} archive img.gz files. Default output is to list file paths to be deleted. See other options.', \
                                 formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=25,width=90))

parser.add_argument('-i', '--input', metavar='DIRECTORY', required=True, \
                    help=f'Release branch directory to prune image files (ex /12.0).')

parser.add_argument('-d', '--delete', action="store_true", help='Delete files instead of only listing them.')

parser.add_argument('-k', '--keep', metavar='RETENTION', required=True, help='Number of days to keep all files.')

parser.add_argument('-r', '--retained', action="store_true", help='List filepaths of images being retained and exit.')

parser.add_argument('-v', '--verbose', action="store_true", help='Enable verbose output (ignored files etc.)')

args = parser.parse_args()


ManageArchive(args).PruneArchive()
