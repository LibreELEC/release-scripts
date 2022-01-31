# Description 
The scripts in the repository are used to generate the releases.json file used in the USB-SD-Creator and in the manual update feature present in LibreELEC 8.0+

The script generates a json formatted output with the filenames, file sizes, and sha256 sums.

For example
```
{  
   "LibreELEC-8.0":{  
      "url":"http://releases.libreelec.tv/",
      "project":{  
         "WeTek_Hub.aarch64":{  
            "displayName":"WeTek Hub",
            "releases":{  
               "0":{  
                  "image":{  
                     "sha256":"bcc1f74fa1deda0db8d873aefb9d154271698982d0503a6a3170ec0c2bc33a59",
                     "name":"LibreELEC-WeTek_Hub.aarch64-7.90.005.img.gz",
                     "size":"116989175"
                  },
                  "file":{  
                     "sha256":"d82ead255190c30c43c3f6bc57962bf5f46863598fd67a31b0e2e5ecb375fbe7",
                     "name":"LibreELEC-WeTek_Hub.aarch64-7.90.005.tar",
                     "size":"128993280"
                  }
               },
```
For the full output see, http://releases.libreelec.tv/releases.json

# How to run
```
python releases.py -i /path/to/releases -u http://releases.yoururl.com/ -o /path/to/releases -v
```
> -i path to releases

> -u top url where the releases are downloadable (http://releases.yoururl.com/my_release-1.1.tar)

> -o path to folder where releases.json is located

> -v verbose output