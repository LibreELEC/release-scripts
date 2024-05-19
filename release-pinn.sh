#!/bin/sh

BASE_DIR="/var/www/releases"
BASE_URL="https://releases.libreelec.tv"
FORCE="no"
COMPRESS="yes"
COPY_TO_MAIN="no"
DEVICES="RPi2 RPi4 RPi5"

DESCRIPTION="A fast and user-friendly Kodi mediacenter distribution"

usage()
{
  cat << EOF
usage: $0 [options...] VERSION
  -d devices    comma separated list of devices (default: RPi2,RPi4,RPi5)
  -f            force overwriting existing versions (default: skip extraction)
  -r            release this version (create pinn/os_list.json)
  -C            disable image compression (default: create .tar.xz images)
  -D directory  base output directory (default: /var/www/releases)
  -U url        base URL (default: https://releases.libreelec.tv)
EOF
}

while getopts d:frCD:U: opt; do
  case "${opt}" in
  d) DEVICES=$(echo "${OPTARG}" | tr ',' ' ');;
  f) FORCE="yes";;
  r) COPY_TO_MAIN="yes";;
  C) COMPRESS="no";;
  D) BASE_DIR="${OPTARG}";;
  U) BASE_URL="${OPTARG}";;
  \?) usage; exit 1;;
  esac
done

shift $((OPTIND - 1))

if [ $# -ne 1 ]; then
  usage
  exit 1
fi

VERSION="$1"

set -e

PINN_DIR="${BASE_DIR}/pinn"
PINN_VERSION_DIR="${PINN_DIR}/${VERSION}"
ICON_FILE="LibreELEC.png"
MARKETING_FILE="marketing.tar"

PINN_ICON_FILE="${PINN_DIR}/${ICON_FILE}"
PINN_MARKETING_FILE="${PINN_DIR}/${MARKETING_FILE}"

if [ "${COMPRESS}" = "yes" ]; then
  SYSTEM_TAR="System.tar.xz"
else
  SYSTEM_TAR="System.tar"
fi

base_setup()
{
  if [ ! -d "${PINN_DIR}" ]; then
    mkdir -p "${PINN_DIR}"
  fi

  if [ ! -e "${PINN_ICON_FILE}" ]; then
    # copy icon from old noobs release
    if [ -e "${BASE_DIR}/noobs/LibreELEC_RPi5/LibreELEC_RPi5.png" ]; then
      cp "${BASE_DIR}/noobs/LibreELEC_RPi5/LibreELEC_RPi5.png" "${PINN_ICON_FILE}"
    else
      echo "error: no LibreELEC.png icon file found, copy it to ${PINN_ICON_FILE}"
      exit 1
    fi
  fi
  
  if [ ! -e "${PINN_MARKETING_FILE}" ]; then
    # copy marketing.tar from old noobs release
    if [ -e "${BASE_DIR}/noobs/LibreELEC_RPi5/marketing.tar" ]; then
      cp "${BASE_DIR}/noobs/LibreELEC_RPi5/marketing.tar" "${PINN_MARKETING_FILE}"
    else
      echo "error: no marketing.tar file found, copy it to ${PINN_MARKETING_FILE}"
      exit 1
    fi
  fi
}

prepare_common()
{
  PINN_TEMP=$(mktemp -d --tmpdir pinn.XXXXXXXXXX)

  trap cleanup 0
}

cleanup()
{
  if [ -n "${PINN_TEMP}" ]; then
    rm -rf "${PINN_TEMP}"
  fi
}

prepare_version()
{
  if [ ! -d "${PINN_VERSION_DIR}" ]; then
    mkdir -p "${PINN_VERSION_DIR}"
  fi
}

# args: update-tar-file
create_system_tar()
{
  update_dir="${PINN_TEMP}/update-tar"
  rm -rf "${update_dir}"
  mkdir -p "${update_dir}"
  tar xf "$1" --strip-components=1 -C "${update_dir}"

  system_dir="${PINN_TEMP}/system"

  rm -rf "${system_dir}"
  rm -f "${PINN_TEMP}/${SYSTEM_TAR}"
  mkdir -p "${system_dir}"
  (
    cd "${update_dir}"
    mv "target/KERNEL" "${system_dir}/kernel.img"
    mv "target/SYSTEM" "${system_dir}"
    mv "3rdparty/bootloader/"* "${system_dir}"

    cd "${system_dir}"
    tar -acf "${PINN_TEMP}/${SYSTEM_TAR}" --owner=root:0 --group=root:0 -- *
  )
  SYSTEM_SIZE=$(du -s -B 1000000 "${system_dir}" | awk '{print $1}' )
  rm -rf "${system_dir}" "${update_dir}"
}

# args: device
get_supported_models()
{
  case "$1" in
  RPi)  echo '[ "Pi Model", "Compute Module Rev", "Pi Zero" ]';;
  RPi2) echo '[ "Pi 2", "Pi 3", "Pi Compute Module 3" ]';;
  RPi4) echo '[ "Pi 4" ]';;
  RPi5) echo '[ "Pi 5" ]';;
  *)    
        echo "unsupported device $1" >&2
        exit 1
        ;;
  esac
}

# args: device
get_target_models()
{
  case "$1" in
  RPi)  echo "RPi 0/1";;
  RPi2) echo "RPi 2/3";;
  RPi4) echo "RPi 4";;
  RPi5) echo "RPi 5";;
  *)    
        echo "unsupported device $1" >&2
        exit 1
        ;;
  esac
}

# args: update_tar
get_release_date()
{
  stat -c %y "$1" | awk '{print $1}'
}

# args: device, dir, release date
create_os_json()
{
  cat > "$2/os.json" << EOF
{
  "name": "LibreELEC_$1",
  "version": "${VERSION}",
  "release_date": "$3",
  "description": "${DESCRIPTION} for $(get_target_models "$1")",
  "username": "root",
  "password": "libreelec",
  "supports_backup": true,
  "group": "Media",
  "url": "https://libreelec.tv/",
  "supported_models": $(get_supported_models "$1")
}
EOF
}

# args: dir, systen size, system sha512
create_partitions_json()
{
cat > "$1/partitions.json" << EOF
{
  "partitions": [
    {
      "label":                     "System",
      "filesystem_type":           "FAT",
      "partition_size_nominal":    512,
      "want_maximised":            false,
      "uncompressed_tarball_size": $2,
      "sha512sum":                 "$3",
      "mkfs_options":              ""
    },
    {
      "label":                     "Storage",
      "empty_fs":                  true,
      "filesystem_type":           "ext4",
      "partition_size_nominal":    512,
      "want_maximised":            true,
      "uncompressed_tarball_size": 1,
      "mkfs_options":              "-m 0"
    }
  ]
}
EOF
}

# args device, dir
create_partition_setup()
{
  case "$1" in
  RPi5) cmdline_args="quiet console=ttyAMA10,115200 console=tty0";;
  *)    cmdline_args="quiet console=tty0";;
  esac

  cat > "$2/partition_setup.sh" <<EOF
#!/bin/sh
set -ex

if [ -z "\${part1}" ] || [ -z "\${part2}" ] || [ -z "\${id1}" ] || [ -z "\${id2}" ]; then
  echo "error: missing environment variables id1/2 or part1/2"
  exit 1
fi

mkdir -p "/tmp/le-boot"
mount "\${part1}" "/tmp/le-boot"
if [ -e "/tmp/le-boot/cmdline.txt" ]; then
  sed -e 's/boot=[^ ]*/boot='"\${id1}/" -e 's/disk=[^ ]*/disk='"\${id2}/" -i "/tmp/le-boot/cmdline.txt"
else
  echo "boot=\${id1} disk=\${id2} ${cmdline_args}" > "/tmp/le-boot/cmdline.txt"
fi
umount "/tmp/le-boot"
rmdir "/tmp/le-boot"
EOF
}

# args: device, update tar, dest dir, release date
extract_device()
{
  device="$1"
  update_tar="$2"
  dest_dir="$3"
  release_date="$4"

  create_system_tar "${update_tar}"

  mkdir -p "${dest_dir}"

  system_tar_sha512=$(sha512sum "${PINN_TEMP}/${SYSTEM_TAR}" | awk '{print $1}')
  mv "${PINN_TEMP}/${SYSTEM_TAR}" "${dest_dir}"
  cp "${PINN_ICON_FILE}" "${PINN_MARKETING_FILE}" "${dest_dir}"

  create_os_json "${device}" "${dest_dir}" "${release_date}"
  create_partitions_json "${dest_dir}" "${SYSTEM_SIZE}" "${system_tar_sha512}"
  create_partition_setup "${device}" "${dest_dir}"
}

# args: device, release date, download size
get_os_entry()
{
  url="${BASE_URL}/pinn/${VERSION}/${DEVICE}"
  cat << EOF
    {
      "os_name": "LibreELEC_$1",
      "description": "${DESCRIPTION} for $(get_target_models "$1")",
      "release_date": "$2",
      "version": "${VERSION}",
      "supported_models": $(get_supported_models "$1"),
      "url": "https://libreelec.tv/",
      "group": "Media",
      "download_size": $3,
      "os_info": "${url}/os.json",
      "partitions_info": "${url}/partitions.json",
      "icon": "${url}/${ICON_FILE}",
      "marketing_info": "${url}/${MARKETING_FILE}",
      "partition_setup": "${url}/partition_setup.sh",
      "tarballs": [
        "${url}/${SYSTEM_TAR}"
      ],
      "nominal_size": 1024
    }
EOF
}
LIST_SEP=",
"

if [ "${COPY_TO_MAIN}" = "yes" ]; then
  echo "Releasing ${VERSION}"
else
  echo "Creating ${VERSION} PINN files"
fi

base_setup
prepare_common
prepare_version

OS_LIST=""

EXTRACTED_FILES="no"

for DEVICE in ${DEVICES}; do
  UPDATE_TAR="${BASE_DIR}/LibreELEC-${DEVICE}.aarch64-${VERSION}.tar"
  if [ ! -e "${UPDATE_TAR}" ]; then
	    UPDATE_TAR="${BASE_DIR}/LibreELEC-${DEVICE}.arm-${VERSION}.tar"
    if [ ! -e "${UPDATE_TAR}" ]; then
      echo "error: no update tar for $DEVICE available, exiting"
      exit 1
    fi
  fi

  release_date=$(get_release_date "${UPDATE_TAR}")

  PINN_DEVICE_DIR="${PINN_VERSION_DIR}/${DEVICE}"

  need_extract="yes"
  if [ -d "${PINN_DEVICE_DIR}" ]; then
    if [ "${FORCE}" = "yes" ]; then
      echo "fored re-extract of ${DEVICE}"
      rm -rf "${PINN_DEVICE_DIR}"
    else
      need_extract="no"
      echo "skipping extract of ${DEVICE}"
    fi
  else
    echo "extracting ${DEVICE}"
  fi

  if [ "${need_extract}" = "yes" ]; then
    extract_device "${DEVICE}" "${UPDATE_TAR}" "${PINN_DEVICE_DIR}" "${release_date}"
    EXTRACTED_FILES="yes"
  fi

  if [ ! -e "${PINN_DEVICE_DIR}/${SYSTEM_TAR}" ]; then
    echo "error: ${PINN_DEVICE_DIR}/${SYSTEM_TAR} is missing"
    exit 1
  fi

  download_size=$(stat -c %s "${PINN_DEVICE_DIR}/${SYSTEM_TAR}" | awk '{print $1}')

  os_entry=$(get_os_entry "${DEVICE}" "${release_date}" "${download_size}")

  if [ -n "${OS_LIST}" ]; then
    OS_LIST="${OS_LIST}${LIST_SEP}"
  fi

  OS_LIST="${OS_LIST}${os_entry}"
done

if [ -z "${OS_LIST}" ]; then
  echo "error: empty OS list"
  exit 1
fi

if [ "${EXTRACTED_FILES}" = "yes" ] || [ ! -e "${PINN_VERSION_DIR}/os_list.json" ]; then
  cat > "${PINN_VERSION_DIR}/os_list.json" << EOF
{
  "os_list": [
${OS_LIST}
  ]
}
EOF

  echo "wrote ${VERSION} OS list to ${PINN_VERSION_DIR}/os_list.json"
fi

if [ "${COPY_TO_MAIN}" = "yes" ]; then
 cp "${PINN_VERSION_DIR}/os_list.json" "${PINN_DIR}/os_list.json"
 echo "wrote release OS list to ${PINN_DIR}/os_list.json"
fi

echo "done."
