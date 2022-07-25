# Description 
The scripts in the repository are used to generate the releases.json file used in the USB-SD-Creator and in the addon's update feature present in LibreELEC 10.0+.

The script generates a json formatted output with the filenames, file sizes, sha256 sums, modification timestamp, and the directory subpath the file resides in.

For example
```
{
  "LibreELEC-10.0": {
    "prettyname_regex": "^LibreELEC-.*-([0-9]+\\.[0-9]+\\-.*-[0-9]{8}-[0-9a-z]{7})",
    "project": {
      "RPi2.arm": {
        "displayName": "Raspberry Pi 2 and 3",
        "releases": {
          "0": {
            "file": {
              "name": "LibreELEC-RPi2.arm-10.0.2.tar",
              "sha256": "3c4f6b848f4e5d700d4389fdd08f9a99cfc1a3c8791d9d803584e4197c69cb19",
              "size": "129945600",
              "subpath": "10.0/RPi",
              "timestamp": "2022-03-05 18:17:34"
            },
            "image": {
              "name": "LibreELEC-RPi2.arm-10.0.2.img.gz",
              "sha256": "9befdc8f42a663e57d7e1e24230fa11354a25cf003ef352c9d3ec576919bea90",
              "size": "126804594",
              "subpath": "10.0/RPi",
              "timestamp": "2022-03-05 18:17:59"
            }
          }
        }
      }
    },
    "url": "https://releases.libreelec.tv/"
  },
```
For the full output see, https://releases.libreelec.tv/releases.json

# How to run
```
python releases.py -i /path/to/releases -u http://releases.yoururl.com/ -o /path/to/releases -v
```
> -i path to releases

> -u top url where the releases are downloadable (http://releases.yoururl.com/my_release-1.1.tar)

> -o path to folder where releases.json is located

> -v verbose output
