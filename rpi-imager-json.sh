#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2023-present Team LibreELEC (https://libreelec.tv)

# Run this script to generate a json file compatible with the RPi Imager Tool
#
# example: "./rpi-imager-json.sh 10.0.4"

if [ $# -eq 0 ]; then
  echo "usage: ${0} VERSION"
  exit 1
fi

# Abort at first error
set -e

VERSION="$1"
RELEASES_DIR="/var/www/releases"
# order here will be the order devices appear in json
DEVICES="RPi4 RPi2 RPi"
IMAGER_JSON="${RELEASES_DIR}/os_list_imagingutility_le.json"

# Compare input against regex
if [[ $VERSION =~ ^[0-9]{1,2}.[0-9].[0-9]{1,3}$ ]]; then
   echo "Creating compatible rpi-imager json file for LibreELEC $VERSION"
else
   echo "ERROR: Not a valid release number!" >&2; exit 1
fi

# CREATE JSON FILE USED BY THE Pi Foundation IMAGER TOOL

# Header
cat > "${IMAGER_JSON}" << EOL
{
    "os_list": [
EOL

FIRST_DEVICE="yes"

for DEVICE in $DEVICES; do
  if [ -f ${RELEASES_DIR}/LibreELEC-${DEVICE}.arm-${VERSION}.img.gz ]; then
    # Generate SHA256
    rpi_sha256="$(gzip -d -c ${RELEASES_DIR}/LibreELEC-${DEVICE}.arm-${VERSION}.img.gz  | sha256sum | cut -d ' ' -f 1)"
    # Generate SIZE
    rpi_size="$(stat -c %s ${RELEASES_DIR}/LibreELEC-${DEVICE}.arm-${VERSION}.img.gz)"
    # Generate CREATE DATE
    rpi_date="$(stat -c %y ${RELEASES_DIR}/LibreELEC-${DEVICE}.arm-${VERSION}.img.gz  | cut -d ' ' -f 1)"
    # Generate EXTRACTED SIZE
    rpi_extracted="$(gzip -l ${RELEASES_DIR}/LibreELEC-${DEVICE}.arm-${VERSION}.img.gz  | sed -n '2p' | awk '{print $2}')"

    case "$DEVICE" in
      RPi)
        DESC="RPi0/RPi1"
        ;;
      RPi2)
        DESC="RPi2/RPi3"
        ;;
      RPi4)
        DESC="RPi4"
        ;;
      *)
        echo "ERROR: unknown device ${DEVICE}!" >&2; exit 1
        ;;
    esac
  else
    echo "INFO: no ${VERSION} image file found for ${DEVICE}"
    continue
  fi
  if [ "$FIRST_DEVICE" = "no" ]; then
    cat >> "${IMAGER_JSON}" << EOL
        },
EOL
  fi
  cat >> "${IMAGER_JSON}" << EOL
        {
            "url": "https://releases.libreelec.tv/LibreELEC-${DEVICE}.arm-${VERSION}.img.gz",
            "extract_size": ${rpi_extracted},
            "extract_sha256": "${rpi_sha256}",
            "image_download_size": ${rpi_size},
            "description": "A fast and user-friendly Kodi mediacenter distro for ${DESC}",
            "icon": "https://releases.libreelec.tv/noobs/LibreELEC_RPi/LibreELEC_RPi.png",
            "name": "LibreELEC (${DESC})",
            "release_date": "${rpi_date}",
            "website": "https://libreelec.tv"
EOL
  FIRST_DEVICE="no"
done

cat >> "${IMAGER_JSON}" << EOL
        }
    ]
}
EOL

exit
