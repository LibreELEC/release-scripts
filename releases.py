#!/usr/bin/env python

# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2016-present Team LibreELEC (https://libreelec.tv)

# requires python >= 3.9

import os
import sys
import re
import argparse
import hashlib
import json
from datetime import datetime, timedelta
from functools import cmp_to_key
from collections import OrderedDict

# x.80.z        => (x+1).0.z  (pre-alpha, use next major train)
# x.90.z        => (x+1).0.z  (alpha, use next major train)
# x.95.z        => (x+1).0.z  (beta/rc, use next major train)
# x.[1,3,5,7].z => x.(y+1).z  (unstable release, use next stable train)
# x.[2,4,6,8].z => x.y.z      (stable release)
#
# x.9.z (an unstable release) is not valid as this will result in x+1.0.z
#
# Examples:
#
#   Version    Train
#   9.0.1      9.0
#   9.1.1      9.2
#   9.2.1      9.2
#   9.80.001   10.0
#   9.90.001   10.0
#   9.95.001   10.0
#   10.0.1     10.0
#   10.1.001   10.2
#
# VERSIONS[0] is label;
# [1] is adjustment to minor version number;
# [2] is the minor version number that corresponds to label;
# [3] (added near EOF) is regex to search version number to know which adjustment to apply
VERSIONS = [
               ['pre-alpha', 0.20, '80',],
               ['alpha',     0.10, '90',],
               ['beta',      0.05, '95',],
               ['rc',        0.03, '97',],
               ['unstable',  0.10, '[1,3,5,7]'],
               ['stable',    0.00, '[0,2,4,6]'],
           ]

DAYS_TO_KEEP_NIGHTLIES=10
JSON_FILE = 'releases.json'
DISTRO_NAME = 'LibreELEC'
PRETTYNAME = f'^{DISTRO_NAME}-.*-([0-9]+\.[0-9]+\.[0-9]+)'
#PRETTYNAME_NIGHTLY = f'^{DISTRO_NAME}-.*-([0-9]+\.[0-9]+\-.*-[0-9]{8}-[0-9a-z]{7})'

class ChunkedHash():
    # Calculate hash for chunked data
    @staticmethod
    def hash_bytestr_iter(bytesiter, hasher, ashexstr=True):
        for block in bytesiter:
            hasher.update(block)
        return (hasher.hexdigest() if ashexstr else hasher.digest())

    # Read file in blocks/chunks to be memory efficient
    @staticmethod
    def file_as_blockiter(afile, blocksize=65536):
        with afile:
          block = afile.read(blocksize)
          while len(block) > 0:
              yield block
              block = afile.read(blocksize)

    # Calculate sha256 hash for a file
    @staticmethod
    def calculate_sha256(fname):
        try:
            return ChunkedHash.hash_bytestr_iter(ChunkedHash.file_as_blockiter(open(fname, 'rb')), hashlib.sha256())
        except Exception:
            raise
            return ''

class ReleaseFile():
    def __init__(self, args):
        self._json_file = JSON_FILE

        self._indir = args.input.removesuffix(os.path.sep)
        self._url = args.url.removesuffix('/')

        if args.output:
            self._outdir = args.output.removesuffix(os.path.sep)
        else:
            self._outdir = self._indir

        self._infile  = os.path.join(self._indir, self._json_file)
        self._outfile = os.path.join(self._outdir, self._json_file)

        if args.prettyname:
            self._prettyname = args.prettyname
        else:
            self._prettyname = PRETTYNAME

        if not os.path.exists(self._indir):
            raise Exception(f'ERROR: invalid path: {self._indir}')

        if not os.path.exists(self._outdir):
            raise Exception(f'ERROR: invalid path: {self._outdir}')

        # nightly image format: {distro}-{proj.device}-{train}-nightly-date-githash{-uboot}.img.gz
        self._regex_nightly_image = re.compile(r'''
            ^(\w+)                   # Distro (alphanumerics)
            -([0-9a-zA-Z_-]+[.]\w+)  # Device (alphanumerics+'-'.alphanumerics)
            -(\d+[.]\d+)             # Train (decimals.decimals)
            -nightly-\d+             # Date (decimals)
            -[0-9a-fA-F]+            # Git Hash (hexadecimals)
            (\S*)                    # Uboot name with leading '-' (non-whitespace)
            \.img\.gz''', re.VERBOSE)

        # nightly tarball format: {distro}-{proj.device}-{train}-nightly-date-githash{-uboot}.tar
        self._regex_nightly_tarball = re.compile(r'''
            ^(\w+)                   # Distro (alphanumerics)
            -([0-9a-zA-Z_-]+[.]\w+)  # Device (alphanumerics.alphanumerics)
            -(\d+[.]\d+)             # Train (decimals.decimals)
            -nightly-\d+             # Date (decimals)
            -[0-9a-fA-F]+            # Git Hash (hexadecimals)
            (\S*)                    # Uboot name with leading '-' (non-whitespace)
            \.tar''', re.VERBOSE)

        # release image format: {distro}-{proj.device}-{maj.min}.bug{-uboot}.img.gz
        self._regex_release_image = re.compile(r'''
            ^(\w+)                   # Distro (alphanumerics)
            -([0-9a-zA-Z_-]+[.]\w+)  # Device (alphanumerics.alphanumerics)
            -(\d+[.]\d+)[.]\d+       # Train (decimals.decimals)
            (\S*)                    # Uboot name with leading '-' (non-whitespace)
            \.img\.gz''', re.VERBOSE)

        # release tarball format: {distro}-{proj.device}-{maj.min}.bug.tar
        self._regex_release_tarball = re.compile(r'''
            ^(\w+)              # Distro (alphanumerics)
            -([0-9a-zA-Z_-]+[.]\w+)        # Device (alphanumerics+'-'.alphanumerics)
            -(\d+[.]\d+)[.]\d+  # Train (decimals.decimals.decimals)
            (\S*)               # Uboot name with leading '-' (non-whitespace)
            \.tar''', re.VERBOSE)

        self.display_name = {'A64.arm': 'Allwinner A64',
                             'AMLGX.arm': 'Amlogic GXBB/GXL/GXM/G12/SM1',
                             'Dragonboard.arm': 'Qualcomm Dragonboard',
                             'FORMAT.any': 'Tools',
                             'Generic.x86_64': 'Generic AMD/Intel/NVIDIA (x86_64)',
                             'H3.arm': 'Allwinner H3',
                             'H5.arm': 'Allwinner H5',
                             'H6.arm': 'Allwinner H6',
                             'imx6.arm': 'NXP i.MX6',
                             'iMX6.arm': 'NXP i.MX6',
                             'iMX8.arm': 'NXP i.MX8',
                             'KVIM.arm': 'Amlogic 3.14',
                             'KVIM2.arm': 'Amlogic 3.14',
                             'Khadas_VIM.arm': 'Amlogic 3.14',
                             'Khadas_VIM2.arm': 'Amlogic 3.14',
                             'LePotato.arm': 'Amlogic 3.14',
                             'MiQi.arm': 'Rockchip RK3288',
                             'Odroid_C2.aarch64': 'Amlogic 3.14',
                             'Odroid_C2.arm': 'Amlogic 3.14',
                             'R40.arm': 'Allwinner R40',
                             'RK3288.arm': 'Rockchip RK3288',
                             'RK3328.arm': 'Rockchip RK3328',
                             'RK3399.arm': 'Rockchip RK3399',
                             'RPi.arm': 'Raspberry Pi Zero and 1',
                             'RPi2.arm': 'Raspberry Pi 2 and 3',
                             'RPi3.arm': 'Raspberry Pi 3',
                             'RPi4.arm': 'Raspberry Pi 4 and 400',
                             'S905.arm': 'Amlogic 3.14',
                             'S912.arm': 'Amlogic 3.14',
                             'Slice.arm': 'Slice CM1/CM3',
                             'Slice3.arm': 'Slice CM1/CM3',
                             'TinkerBoard.arm': 'Rockchip RK3288',
                             'Virtual.x86_64': 'Virtual x86_64',
                             'WeTek_Core.arm': 'Amlogic 3.10',
                             'WeTek_Hub.aarch64': 'Amlogic 3.14',
                             'WeTek_Hub.arm': 'Amlogic 3.14',
                             'WeTek_Play.arm': 'Amlogic 3.10',
                             'WeTek_Play_2.aarch64': 'Amlogic 3.14',
                             'WeTek_Play_2.arm': 'Amlogic 3.14',
                            }

        self.update_json = {}

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass

    # provide version number; returns version number adjusted to stable release train
    def get_train_major_minor(self, item):
        for version in VERSIONS:
            match = VERSIONS[version]['regex'].search(item)
            if match:
                adjust = VERSIONS[version]['adjust']
                item_maj_min = float(match.group(0)) + adjust
                return f'{item_maj_min:.1f}'
        return None

    def get_details(self, path, train, build, file):
        key = f'{train};{build};{file}'
        if key not in self.oldhash:
            print(f'Adding: {file} to {train} train')
            # Use .sha256 file's checksum if present
            if os.path.exists(os.path.join(path, f'{file}.sha256')):
                if args.verbose:
                    print(f'  Using sha256sum from: {file}.sha256')
                with open(os.path.join(path, f'{file}.sha256'), 'r') as f:
                    digest_contents = f.read()
                file_digest = digest_contents.split(' ')[0]
            else:
                file_digest = ChunkedHash().calculate_sha256(os.path.join(path, file))
            file_size = str(os.path.getsize(os.path.join(path, file)))
            file_timestamp = datetime.fromtimestamp(os.path.getmtime(os.path.join(path,file))).isoformat(sep=' ', timespec='seconds')
        else:
            file_digest = self.oldhash[key]['sha256']
            file_size = self.oldhash[key]['size']
            file_timestamp = self.oldhash[key]['timestamp']

        return (file_digest, file_size, file_timestamp)

    def UpdateAll(self):
        self.ReadFile()
        self.UpdateFile()
        self.WriteFile()

    def UpdateFile(self):
        path = self._indir
        url = f'{self._url}/'
        nightly_retention = datetime.now() - timedelta(days=DAYS_TO_KEEP_NIGHTLIES)

        # Walk top level source directory, selecting files for subsequent processing.
        #
        # We're interested in 'LibreELEC-.*.(tar|img.gz)' files, but not '.*-noobs.tar' files.
        list_of_files = []
        list_of_filenames = []
        releases = []
        builds = []
        for (dirpath, dirnames, filenames) in os.walk(path):
            if 'archive' in dirpath or 'upload' in dirpath:
                if args.verbose:
                    print(f'Skipping directory: {dirpath}')
                continue
            for f in filenames:
                if f.startswith(f'{DISTRO_NAME}-'):
                    if f.endswith('.tar') and not f.endswith('-noobs.tar'):
                        # nightly tarballs
                        if 'nightly' in f:
                            if not args.all and datetime.fromtimestamp(os.path.getmtime(os.path.join(dirpath, f))) < nightly_retention:
                                if args.verbose:
                                    print(f'Old nightly: {f}')
                                continue
                            try:
                                parsed_fname = self._regex_nightly_tarball.search(f)
                            except Exception:
                                print(f'Failed to parse filename: {f}')
                                continue
                        # release tarballs
                        else:
                            try:
                                parsed_fname = self._regex_release_tarball.search(f)
                            except Exception:
                                print(f'Failed to parse filename: {f}')
                                continue
                    elif f.endswith('.img.gz'):
                        # nightly images
                        if 'nightly' in f:
                            if not args.all and datetime.fromtimestamp(os.path.getmtime(os.path.join(dirpath, f))) < nightly_retention:
                                if args.verbose:
                                    print(f'Old nightly: {f}')
                                continue
                            try:
                                parsed_fname = self._regex_nightly_image.search(f)
                            except Exception:
                                print(f'Failed to parse filename: {f}')
                                continue
                        else:
                        # release images
                            try:
                                parsed_fname = self._regex_release_image.search(f)
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
                    fname_train = parsed_fname.group(3)
                    fname_uboot = parsed_fname.group(4).removeprefix('-')

                    distro_train = f'{fname_distro}-{self.get_train_major_minor(fname_train)}'
                    if distro_train not in releases:
                        if args.verbose:
                            print(f'Adding to releases: {distro_train}')
                        releases.append(distro_train)

                    if fname_device not in builds:
                        if args.verbose:
                            print(f'Adding to builds: {fname_device}')
                        builds.append(fname_device)

                    list_of_files.append([f, distro_train, fname_device, fname_uboot, dirpath])
                    list_of_filenames.append(f)
                else:
                    if args.verbose:
                        print(f'Ignored file: {f}')
                    continue

        # Sort list of release trains (8.0, 8.2, 9.0 etc.)
        trains = []

        for train in sorted(releases):
            trains.append(train)
        if args.verbose:
            print(trains)

        # Add train data to json
        for train in trains:
            self.update_json[train] = {'url': url}
            self.update_json[train]['prettyname_regex'] = self._prettyname
            self.update_json[train]['project'] = {}

        # Sort list of builds (eg. RPi2.arm, Generic.x86_64 etc.)
        builds = sorted(builds)
        if args.verbose:
            print(builds)

        for train in trains:     # ex: LibreELEC-10.0
            for build in builds: # ex: RPi2.arm
                entries = {}
                for release_file in list(list_of_files): # copy so original may be modified

                    # file may have been processed on a previous loop
                    if release_file not in list_of_files:
                        continue

                    entry = {}
                    entry_position = len(entries)

                    if train in release_file and build in release_file:

                        base_filename = release_file[0].removesuffix('.tar')
                        base_filename = base_filename.removesuffix('.img.gz')

                        (file_digest, file_size, file_timestamp) = self.get_details(release_file[4], train, build, release_file[0])

                        # *.tar
                        if release_file[0].endswith('.tar'):
                            entry['file'] = {'name': release_file[0], 'sha256': file_digest, 'size': file_size, 'timestamp': file_timestamp, 'subpath': release_file[4].removeprefix(f'{self._indir}/')}
                            list_of_files.remove(release_file)
                            list_of_filenames.remove(release_file[0])
                            # check for image files with same name so they may be added
                            if f'{base_filename}.img.gz' in list_of_filenames:
                                for image_file in list(list_of_files):
                                    if f'{base_filename}.img.gz' == image_file[0]:
                                        (file_digest, file_size, file_timestamp) = self.get_details(image_file[4], train, build, image_file[0])
                                        entry['image'] = {'name': image_file[0], 'sha256': file_digest, 'size': file_size, 'timestamp': file_timestamp, 'subpath': image_file[4].removeprefix(f'{self._indir}/')}
                                        list_of_files.remove(image_file)
                                        list_of_filenames.remove(image_file[0])
#                            else:
#                                entry['image'] = {'name': '', 'sha256': '', 'size': '', 'timestamp': '', 'subpath': ''}
                        # *-{uboot}.img.gz
                        elif release_file[3]:
                            uboot = []
                            uboot.append({'name': release_file[0], 'sha256': file_digest, 'size': file_size, 'timestamp': file_timestamp, 'subpath': release_file[4].removeprefix(f'{self._indir}/')})
                            list_of_files.remove(release_file)
                            list_of_filenames.remove(release_file[0])
                            # check for similar uboot releases
                            for item in list(list_of_filenames):
                                if item.startswith(base_filename.removesuffix(f'-{release_file[3]}')):
                                    for image_file in list(list_of_files):
                                        if image_file[0].startswith(base_filename.removesuffix(f'-{release_file[3]}')):
                                            (file_digest, file_size, file_timestamp) = self.get_details(image_file[4], train, build, image_file[0])
                                            uboot.append({'name': image_file[0], 'sha256': file_digest, 'size': file_size, 'timestamp': file_timestamp, 'subpath': image_file[4].removeprefix(f'{self._indir}/')})
                                            list_of_files.remove(image_file)
                                            list_of_filenames.remove(image_file[0])

                            entry['uboot'] = uboot
                        # *.img.gz
                        elif release_file[0].endswith('.img.gz'):
                            entry['image'] = {'name': release_file[0], 'sha256': file_digest, 'size': file_size, 'timestamp': file_timestamp, 'subpath': release_file[4].removeprefix(f'{self._indir}/')}
                            list_of_files.remove(release_file)
                            list_of_filenames.remove(release_file[0])
                            # check for tarball files with same name so they may be added
                            if f'{base_filename}.tar' in list_of_filenames:
                                for tarball_file in list(list_of_files):
                                    if f'{base_filename}.tar' == tarball_file[0]:
                                        (file_digest, file_size, file_timestamp) = self.get_details(tarball_file[4], train, build, tarball_file[0])
                                        entry['file'] = {'name': tarball_file[0], 'sha256': file_digest, 'size': file_size, 'timestamp': file_timestamp, 'subpath': tarball_file[4].removeprefix(f'{self._indir}/')}
                                        list_of_files.remove(tarball_file)
                                        list_of_filenames.remove(tarball_file[0])
#                            else:
#                                entry['file'] = {'name': '', 'sha256': '', 'size': '', 'timestamp': '', 'subpath': ''}

                        entries[entry_position] = entry

                # adds each file "grouping" as its own release
                if len(entries) > 0:
                    if build in self.display_name:
                        self.update_json[train]['project'][build] = {'displayName': self.display_name[build], 'releases': entries}
                    else:
                        self.update_json[train]['project'][build] = {'displayName': build, 'releases': entries}

    # Read old file if it exists, to avoid recalculating hashes when possible
    def ReadFile(self):
        self.oldhash = {}
        if os.path.exists(self._infile):
            try:
                with open(self._infile, 'r') as f:
                    oldjson = json.loads(f.read())
                    if args.verbose:
                        print(f'Read old json: {self._infile}')

                for train in oldjson:
                    for build in oldjson[train]['project']:
                        for release in oldjson[train]['project'][build]['releases']:
                            try:
                                data = oldjson[train]['project'][build]['releases'][release]['file']
                                if args.verbose:
                                    print(f'Found old json entry for: {data["name"]}')
                                self.oldhash[f'{train};{build};{data["name"]}'] = {'sha256': data['sha256'], 'size': data['size'], 'timestamp': data['timestamp']}
                            except KeyError:
                                pass
                            try:
                                data = oldjson[train]['project'][build]['releases'][release]['image']
                                if args.verbose:
                                    print(f'Found old json entry for: {data["name"]}')
                                self.oldhash[f'{train};{build};{data["name"]}'] = {'sha256': data['sha256'], 'size': data['size'], 'timestamp': data['timestamp']}
                            except KeyError:
                                pass
                            try:
                                for data in oldjson[train]['project'][build]['releases'][release]['uboot']:
                                    if args.verbose:
                                        print(f'Found old json entry for: {data["name"]}')
                                    self.oldhash[f'{train};{build};{data["name"]}'] = {'sha256': data['sha256'], 'size': data['size'], 'timestamp': data['timestamp']}
                            except KeyError:
                                pass
            except Exception as e:
                print(f'WARNING: Failed to read old json: {self._infile}\n  {e}')
                self.oldhash = {}

    # Write a new file
    def WriteFile(self):
        with open(self._outfile, 'w') as f:
            f.write(json.dumps(self.update_json, indent=2, sort_keys=True))

#---------------------------------------------

# Python3 will return map items in the same order they are added/created, but
# Python2 will return the map in a random order, so convert the map to an OrderedDict()
# to ensure the processing order of the map is consistently top to bottom.
# Also pre-compile the regex as this is more efficient.
_ = OrderedDict()
for item in VERSIONS:
    _[item[0]] = {'adjust': item[1],
                  'minor': item[2],
                  'regex': re.compile(fr'([0-9]+\.{item[2]})')}
VERSIONS = _


parser = argparse.ArgumentParser(description=f'Update {DISTRO_NAME} {JSON_FILE} with available tar/img.gz files.', \
                                 formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=25,width=90))

parser.add_argument('-i', '--input', metavar='DIRECTORY', required=True, \
                    help=f'Directory to parsed (release files, and any existing {JSON_FILE}). By default, {JSON_FILE} will be ' \
                         'written into this directory. Required property.')

parser.add_argument('-u', '--url', metavar='URL', required=True, \
                    help=f'Base URL for {JSON_FILE}. Required property.')

parser.add_argument('-o', '--output', metavar='DIRECTORY', required=False, \
                    help=f'Optional directory into which {JSON_FILE} will be written. Defaults to same directory as --input.')

parser.add_argument('-p', '--prettyname', metavar='REGEX', required=False, \
                    help=f'Optional prettyname regex, default is {PRETTYNAME}')

parser.add_argument('-v', '--verbose', action="store_true", help='Enable verbose output (ignored files etc.)')

parser.add_argument('-a', '--all', action="store_true", required=False, \
                    help='Add all nightly tar/img.gz files without regard to rentention period.')

args = parser.parse_args()

ReleaseFile(args).UpdateAll()
