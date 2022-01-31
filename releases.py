#!/usr/bin/env python

# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2016-present Team LibreELEC (https://libreelec.tv)

import os
import sys
import re
import argparse
import hashlib
import json
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
VERSIONS = [
               ['pre-alpha', 0.20, '80',],
               ['alpha',     0.10, '90',],
               ['beta',      0.05, '95',],
               ['rc',        0.03, '97',],
               ['unstable',  0.10, '[1,3,5,7]'],
               ['stable',    0.00, '[0,2,4,6]'],
           ]

JSON_FILE = 'releases.json'

DISTRO_NAME = 'LibreELEC'

PRETTYNAME = '^%s-.*-([0-9]+\.[0-9]+\.[0-9]+)' % DISTRO_NAME

PRETTYNAME_NIGHTLY = '^LibreELEC-.*-([0-9]+\.[0-9]+\-.*-[0-9]{8}-[0-9a-z]{7})' % DISTRO_NAME

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
        except:
            raise
            return ''

class ReleaseFile():
    def __init__(self, args):
        self._json_file = JSON_FILE

        self._indir = args.input.rstrip(os.path.sep)
        self._url = args.url.rstrip('/')

        if args.output:
            self._outdir = args.output.rstrip(os.path.sep)
        else:
            self._outdir = self._indir

        self._infile  = os.path.join(self._indir, self._json_file)
        self._outfile = os.path.join(self._outdir, self._json_file)

        if args.prettyname:
            self._prettyname = args.prettyname
        else:
            self._prettyname = PRETTYNAME

        if not os.path.exists(self._indir):
            raise Exception('ERROR: %s is not a valid path' % self._indir)

        if not os.path.exists(self._outdir):
            raise Exception('ERROR: %s is not a valid path' % self._outdir)

        self._regex_xyz_custom_sort = re.compile(r'([0-9]+)\.([0-9]+)\.([0-9]+)')
        self._regex_xydate_custom_sort = re.compile(r'([0-9]+)\.([0-9]+)-.*-([0-9]{14})-')
        self._regex_xydate_custom_short_sort = re.compile(r'([0-9]+)\.([0-9]+)-.*-([0-9]{8})-')
        self._regex_builds = re.compile(r'%s-([^-]*)-.*' % DISTRO_NAME)

        self.display_name = {'A64.arm': 'Allwinner A64',
                             'AMLG12.arm': 'Amlogic G12A/G12B/SM1',
                             'AMLGX.arm': 'Amlogic GXBB/GXL/GXM',
                             'Dragonboard.arm': 'Qualcomm Dragonboard',
                             'FORMAT.any': 'Tools',
                             'Generic.x86_64': 'Generic AMD/Intel/NVIDIA (x86_64)',
                             'H3.arm': 'Allwinner H3',
                             'H6.arm': 'Allwinner H6',
                             'imx6.arm': 'NXP i.MX6',
                             'iMX6.arm': 'NXP i.MX6',
                             'KVIM.arm': 'Khadas VIM',
                             'KVIM2.arm': 'Khadas VIM-2',
                             'Khadas_VIM.arm': 'Khadas VIM',
                             'Khadas_VIM2.arm': 'Khadas VIM-2',
                             'LePotato.arm': 'LePotato',
                             'MiQi.arm': 'Mqmaker MiQi',
                             'Odroid_C2.aarch64': 'Odroid C2',
                             'Odroid_C2.arm': 'Odroid C2',
                             'RK3328.arm': 'Rockchip RK3328',
                             'RK3399.arm': 'Rockchip RK3399',
                             'RPi.arm': 'Raspberry Pi Zero and 1',
                             'RPi2.arm': 'Raspberry Pi 2 and 3',
                             'RPi4.arm': 'Raspberry Pi 4',
                             'S905.arm': 'Amlogic S905/X/D/W',
                             'S912.arm': 'Amlogic S912',
                             'Slice.arm': 'Slice (CM1)',
                             'Slice3.arm': 'Slice (CM3)',
                             'TinkerBoard.arm': 'ASUS TinkerBoard',
                             'Virtual.x86_64': 'Virtual x86_64',
                             'WeTek_Core.arm': 'WeTek Core',
                             'WeTek_Hub.aarch64': 'WeTek Hub',
                             'WeTek_Hub.arm': 'WeTek Hub',
                             'WeTek_Play.arm': 'WeTek Play',
                             'WeTek_Play_2.aarch64': 'WeTek Play 2',
                             'WeTek_Play_2.arm': 'WeTek Play 2',
                            }

        self.update_json = {}

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass

    def get_train_major_minor(self, item):
        for version in VERSIONS:
            match = VERSIONS[version]['regex'].search(item)
            if match:
                adjust = VERSIONS[version]['adjust']
                item_maj_min = float(match.groups(0)[0]) + adjust
                return '%s-%0.1f' % (DISTRO_NAME, item_maj_min)
        return None

    def match_version(self, item, build, train):
        train_items = train.split('-')

        major_minor = train_items[1]

        if item.startswith('%s-%s-' % (DISTRO_NAME, build)) and \
           train == self.get_train_major_minor(item):
           return True

        return False

    def custom_sort_train(self, a, b):
        a_items = a.split('-')
        b_items = b.split('-')

        a_builder = a_items[0]
        b_builder = b_items[0]

        if (a_builder == b_builder):
          return (float(a_items[1]) - float(b_items[1]))
        elif (a_builder < b_builder):
          return -1
        elif (a_builder > b_builder):
          return +1

    def custom_sort_release(self, a, b):
        a_maj_min_patch = self._regex_xyz_custom_sort.search(a)
        if not a_maj_min_patch:
            a_maj_min_patch = self._regex_xydate_custom_sort.search(a)

        if not a_maj_min_patch:
            a_maj_min_patch = self._regex_xydate_custom_short_sort.search(a)

        b_maj_min_patch = self._regex_xyz_custom_sort.search(b)
        if not b_maj_min_patch:
            b_maj_min_patch = self._regex_xydate_custom_sort.search(b)

        if not b_maj_min_patch:
            b_maj_min_patch = self._regex_xydate_custom_short_sort.search(b)

        a_int = int('%04d%04d%014d' % (int(a_maj_min_patch.groups(0)[0]), int(a_maj_min_patch.groups(0)[1]), int(a_maj_min_patch.groups(0)[2])))
        b_int = int('%04d%04d%014d' % (int(b_maj_min_patch.groups(0)[0]), int(b_maj_min_patch.groups(0)[1]), int(b_maj_min_patch.groups(0)[2])))

        return (a_int - b_int)

    def get_details(self, path, train, build, file):
        key = '%s;%s;%s' % (train, build, file)
        if key not in self.oldhash:
            print('Adding: %s in %s train' % (file, train))
            file_digest = ChunkedHash().calculate_sha256(os.path.join(path, file))
            file_size = str(os.path.getsize(os.path.join(path, file)))
        else:
            file_digest = self.oldhash[key]['sha256']
            file_size = self.oldhash[key]['size']

        return (file_digest, file_size)

    def UpdateAll(self):
        self.ReadFile()

        self.UpdateFile()

        self.WriteFile()

    def UpdateCombinedFile(self):
        self.ReadFile()

        for (dirpath, dirnames, filenames) in os.walk(self._indir):
            for project in dirnames:
                self.UpdateFile(project)
            break

        self.WriteFile()

    def UpdateProjectFile(self, project):
        self.ReadFile()

        self.UpdateFile(project)

        self.WriteFile()

    def UpdateFile(self, project=None):
        if project:
            path = os.path.join(self._indir, project)
            url = '%s/%s/' % (self._url, project)
        else:
            path = self._indir
            url = '%s/' % self._url

        # Walk top level source directory, selecting files for subsequent processing.
        #
        # We're only interested in 'LibreELEC-.*.tar' files, and not interested
        # in '.*-noobs.tar' files.
        #
        # img.gz files will be included in the output if there is a matching
        # img.gz for the tar file.
        #
        files = []
        images = []
        for (dirpath, dirnames, filenames) in os.walk(path):
            for f in filenames:
                if f.startswith('%s-' % DISTRO_NAME):
                    if f.endswith('.tar') and not f.endswith('-noobs.tar'):
                        files.append(f)
                    elif f.endswith('.img.gz'):
                        images.append(f)
            break

        # From files, identify all release trains (8.0, 8.0, 8.2, 9.0 etc.)
        releases = []
        for release in files:
            train_major_minor = self.get_train_major_minor(release)
            if train_major_minor:
                releases.append(train_major_minor)
            elif args.verbose:
                print('IGNORED [Failed to match any train]: %s' % release)

        # Create a unique sorted list of release trains (8.0, 8.2, 9.0 etc.)
        trains = []

        for train in sorted(list(set(releases)), key=cmp_to_key(self.custom_sort_train)):
            trains.append(train)

        print(trains)

        # Create a unique sorted list of builds (eg. RPi2.arm, Generix.x86_64 etc.)
        builds = []
        for release in files:
            if self._regex_builds.match(release):
                builds.append(self._regex_builds.findall(release)[0])
        builds = sorted(list(set(builds)))

        print(builds)

        # For each train, add or update each matching build (tar and img.gz)
        for train in trains:
            self.update_json[train] = {'url': url}
            self.update_json[train]['prettyname_regex'] = self._prettyname
            self.update_json[train]['project'] = {}

            for build in builds:
                releases = sorted([x for x in files if self.match_version(x, build, train)], key=cmp_to_key(self.custom_sort_release))

                entries = {}
                for i, release in enumerate(releases):
                    entry = {'file': {}}

                    # .tar
                    (file_digest, file_size) = self.get_details(path, train, build, release)
                    entry['file'] = {'name': release, 'sha256': file_digest, 'size': file_size}

                    # .img.gz
                    image = re.sub('\.tar$', '.img.gz', release)
                    if image in images:
                        (file_digest, file_size) = self.get_details(path, train, build, image)
                    else:
                        image = file_digest = file_size = ''
                    entry['image'] = {'name': image, 'sha256': file_digest, 'size': file_size}

                    # u-boot board-specific .img.gz
                    uboot = []
                    for image in sorted([x for x in images if x.startswith(re.sub('\.tar$', '-', release))]):
                        (file_digest, file_size) = self.get_details(path, train, build, image)
                        uboot.append({'name': image, 'sha256': file_digest, 'size': file_size})
                    # Add u-boot if we have any entries, remove if not
                    if uboot != []:
                        entry['uboot'] = uboot

                    entries[i] = entry

                # Only add builds with releases
                if len(entries) != 0:
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
                    for train in oldjson:
                        for build in oldjson[train]['project']:
                            for release in oldjson[train]['project'][build]['releases']:
                                r = oldjson[train]['project'][build]['releases'][release]['file']
                                self.oldhash['%s;%s;%s' % (train, build, r['name'])] = {'sha256': r['sha256'], 'size': r['size']}
                                try:
                                    i = oldjson[train]['project'][build]['releases'][release]['image']
                                    self.oldhash['%s;%s;%s' % (train, build, i['name'])] = {'sha256': i['sha256'], 'size': i['size']}
                                except:
                                    pass
                                try:
                                    for i in oldjson[train]['project'][build]['releases'][release]['uboot']:
                                        self.oldhash['%s;%s;%s' % (train, build, i['name'])] = {'sha256': i['sha256'], 'size': i['size']}
                                except:
                                    pass
            except:
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
                  'regex': re.compile(r'-([0-9]+\.%s)[-.]' % item[2])}
VERSIONS = _

parser = argparse.ArgumentParser(description='Update %s %s with available tar/img.gz files.' % (DISTRO_NAME, JSON_FILE), \
                                 formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=25,width=90))

parser.add_argument('-i', '--input', metavar='DIRECTORY', required=True, \
                    help='Directory to parsed (release files, and any existing %s). By default %s will be ' \
                         'written into this directory. Required property.' % (JSON_FILE, JSON_FILE))

parser.add_argument('-u', '--url', metavar='URL', required=True, \
                    help='Base URL for %s. Required property.' % JSON_FILE)

parser.add_argument('-o', '--output', metavar='DIRECTORY', required=False, \
                    help='Optional directory into which %s will be written. Defaults to same directory as --input.' % JSON_FILE)

parser.add_argument('-p', '--prettyname', metavar='REGEX', required=False, \
                    help='Optional prettyname regex, default is %s' % PRETTYNAME)

parser.add_argument('-v', '--verbose', action="store_true", help='Enable verbose output (ignored files etc.)')

args = parser.parse_args()

ReleaseFile(args).UpdateAll()
