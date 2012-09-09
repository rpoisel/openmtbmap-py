#!/usr/bin/python

# Written by Rainer Poisel <rainer.poisel@gmail.com>
# Released under the GPLv3 License

import sys
import os
import os.path
import subprocess
import shutil
import fnmatch
import argparse
import traceback
import pycurl

# commands required:
# * cp thinat.TYP 01002468.TYP
# * wine gmt.exe -wy 7352 01002468.TYP
# * wine gmt.exe -j -o gmapsupp.img -f 7352 \
#        -m "openmtbmap_srtm" 6*.img 7*.img 01002468.TYP


class CurlWriter(object):
    def __init__(self, pFile):
        self.__mFile = pFile
        self.__mFH = None

    def body_callback(self, pBuffer):
        if self.__mFH is None:
            self.__mFH = open(self.__mFile, "wb")
        self.__mFH.write(pBuffer)

    def close(self):
        if self.__mFH is not None:
            self.__mFH.close()


class CGeneratorContext(object):
    cmd_wine = 'wine'
    cmd_gmt = 'gmt.exe'
    cmd_curl = 'curl'
    cmd_sevenzip = '7z'
    default_verbose = False
    default_forceextract = False
    default_gmapsupp_img = 'gmapsupp.img'
    default_wd = '.'
    default_pattern = "[7,6]*.img"
    default_download_dir = '.'
    default_layout = 'thin'
    default_download_file = None

    @staticmethod
    def is_exe(pPath):
        return os.path.exists(pPath) and os.access(pPath, os.X_OK)

    @staticmethod
    def which(pProgram):
        lFPath, lFName = os.path.split(pProgram)
        if lFPath:
            if CGeneratorContext.is_exe(pProgram):
                return pProgram
        else:
            for lPath in os.environ["PATH"].split(os.pathsep):
                lExecFile = os.path.join(lPath, pProgram)
                if CGeneratorContext.is_exe(lExecFile):
                    return lExecFile

        return None

    def __init__(self, pWorkingDir):
        self.__mWorkingDir = pWorkingDir
        self.__mCommandPrefix = []
        if os.name == 'posix':
            if CGeneratorContext.which(CGeneratorContext.cmd_wine) is None:
                raise Exception(CGeneratorContext.cmd_wine +
                        " needs to be installed to run " +
                        CGeneratorContext.cmd_gmt + " under POSIX-OSes.")
            self.__mCommandPrefix.append(CGeneratorContext.cmd_wine)

    def run_gmt(self, pArgs):
        if not os.path.exists(os.path.join(self.__mWorkingDir,
                CGeneratorContext.cmd_gmt)):
            raise Exception(os.path.join(self.__mWorkingDir,
            CGeneratorContext.cmd_gmt) + """ not found. \
Please put gmt.exe into the same folder in \
which the maps and this batch are placed. Make \
sure """ + CGeneratorContext.cmd_gmt + """ is
version 048a or later (gmt.exe included with \
contourlines download is outdated). \
""" + CGeneratorContext.cmd_gmt + """ is part of gmaptool
which you can download here: \
http://www.anpo.republika.pl/download.html#gmaptool
""")
        lProcess = subprocess.Popen(self.__mCommandPrefix +
                [os.path.join(self.__mWorkingDir, CGeneratorContext.cmd_gmt)] +
                pArgs, stderr=subprocess.PIPE)
        return (lProcess.wait(), lProcess.stderr.read())

    def run_curl(self, pLocalFile, pUrl):
        lWriter = CurlWriter(pLocalFile)
        lCurl = pycurl.Curl()
        lCurl.setopt(pycurl.URL, pUrl)
        lCurl.setopt(pycurl.FOLLOWLOCATION, 1)
        lCurl.setopt(pycurl.MAXREDIRS, 5)
        lCurl.setopt(pycurl.CONNECTTIMEOUT, 30)
        lCurl.setopt(pycurl.TIMEOUT, 3600)
        lCurl.setopt(pycurl.NOSIGNAL, 1)
        if os.path.exists(pLocalFile):
            lCurl.setopt(pycurl.TIMECONDITION, pycurl.TIMECONDITION_IFMODSINCE)
            lCurl.setopt(pycurl.TIMEVALUE, int(os.path.getmtime(pLocalFile)))
        lCurl.setopt(pycurl.WRITEFUNCTION, lWriter.body_callback)
        lCurl.perform()
        lCurl.close()
        lWriter.close()

    def run_sevenzip(self, pArgs):
        lProcess = subprocess.Popen([CGeneratorContext.cmd_sevenzip] +
                pArgs, stderr=subprocess.PIPE)
        return (lProcess.wait(), lProcess.stderr.read())

    def correct_typ(self, pFID, pTarget):
        # wine gmt.exe -wy 7352 01002468.TYP
        self.run_gmt(["-wy", pFID, pTarget])

    def join_maps(self, pFID, pTypefile, pOSMMaps, pSRTMMaps, pGmapsuppFile):
        # wine gmt.exe -j -o gmapsupp.img -f 7352 -m "openmtbmap_srtm" \
        #        6*.img 7*.img 01002468.TYP
        lArgs = ["-j", "-o", pGmapsuppFile, "-f", pFID, "-m",
                "openmtbmap_srtm"]
        lArgs += pOSMMaps
        lArgs += pSRTMMaps
        lArgs.append(pTypefile)
        self.run_gmt(lArgs)

    def generate_gmapsupp(self, pType, pGmapsuppFile, pPattern):
        lTypefile = os.path.join(self.__mWorkingDir, "01002468.TYP")
        lFID = ""
        lOSMMaps = []
        lSRTMMaps = []

        # find typefile
        lTypFile = ""
        for lFile in os.listdir(self.__mWorkingDir):
            if fnmatch.fnmatch(lFile, pType + "*.TYP"):
                lTypFile = lFile
                break
        if lTypFile == "":
            raise LookupError("Typefile not found (" + pType + ")")
        # cp thinat.TYP 01002468.TYP
        shutil.copyfile(os.path.join(self.__mWorkingDir, lTypFile),
                lTypefile)

        # determine FID and Map files
        for lFile in os.listdir(self.__mWorkingDir):
            if fnmatch.fnmatch(lFile, pPattern):
                lOSMMaps.append(os.path.join(self.__mWorkingDir, lFile))

        if len(lOSMMaps) > 0 and len(lSRTMMaps) > 0:
            lFID = "7352"
        elif len(lOSMMaps) > 0:
            lFID = "7350"
        elif len(lSRTMMaps) > 0:
            lFID = "7351"
        else:
            raise NameError("Could not determine FID. No maps present?")

        self.correct_typ(lFID, lTypefile)
        self.join_maps(lFID, lTypefile, lOSMMaps, lSRTMMaps, pGmapsuppFile)


def main():
    lParser = argparse.ArgumentParser(description="OpenMTBMap Accumulator",
                  epilog="Example: python " + sys.argv[0] +
                   " -g gmapsupp.img -w \\ /mnt/pod/geo/osm/openmtbmap" +
                   " -p '[7,6]*.img' -d \\ "
                   "/mnt/pod/geo/osm/openmtbmap.txt -l thin")
    lOptionDescs = []
    lOptionDescs.append({'short': '-v',
        'long': '--verbose',
        'action': 'store_true',
        'dest': 'verbose',
        'help': "Be moderately verbose",
        'default': CGeneratorContext.default_verbose})
    lOptionDescs.append({'short': '-g',
        'long': '--gmapsupp',
        'action': 'store',
        'dest': 'gmapsupp',
        'help': "The destination image file",
        'default': CGeneratorContext.default_gmapsupp_img})
    lOptionDescs.append({'short': '-w',
        'long': '--working-dir',
        'action': 'store',
        'dest': 'wd',
        'help': "The working directory",
        'default': CGeneratorContext.default_wd})
    lOptionDescs.append({'short': '-e',
        'long': '--force-extract',
        'action': 'store_true',
        'dest': 'forceextract',
        'help': "Force extraction of archives",
        'default': CGeneratorContext.default_forceextract})
    lOptionDescs.append({'short': '-p',
        'long': '--pattern',
        'action': 'store',
        'dest': 'pattern',
        'help': """Pattern for imagefiles to combine. DO NOT FORGET TO
        ESCAPE THE PATTERN! PREVENT THE SHELL FROM REPLACING IT WITH
        MATCHES BY USING TICKS (E. G. \'*.img\')""",
        'default': CGeneratorContext.default_pattern})
    lOptionDescs.append({'short': '-d',
        'long': '--download',
        'action': 'store',
        'dest': 'download',
        'help': """Batch mode for automatic download and compilation of
        OpenMTBMaps.""",
        'default': CGeneratorContext.default_download_file})
    lOptionDescs.append({'short': '-l',
        'long': '--layout',
        'action': 'store',
        'dest': 'layout',
        'help': """clas for clas*.TYP (classic layout - optimized for \
Vista/Legend series)
            thin for thin*.TYP (thinner tracks and pathes - optimized \
for Gpsmap60/76 series)
            wide for wide*.TYP (high contrast layout, like classic but \
with white forest - optimized for Oregon/Colorado dull displays)
            trad for trad*.TYP Big Screen layout. Do not use on GPS.""",
        'default': CGeneratorContext.default_layout})

    for lOptionDesc in lOptionDescs:
        lParser.add_argument(lOptionDesc['short'],
            lOptionDesc['long'],
                action=lOptionDesc['action'],
                dest=lOptionDesc['dest'],
                default=lOptionDesc['default'],
                help=lOptionDesc['help'])
    lOptions = lParser.parse_args()

    if len(sys.argv) == 1:
        lParser.print_help()
        sys.exit(0)

    try:
        lContext = CGeneratorContext(lOptions.wd)
        lDirDownload = os.path.join(lOptions.wd,
                CGeneratorContext.default_download_dir)

        if lOptions.download is not None:
            # create download directory if it does not exist in the wd
            if not os.path.exists(os.path.join(lOptions.wd,
                CGeneratorContext.default_download_dir)):
                os.makedirs(os.path.join(lOptions.wd,
                        CGeneratorContext.default_download_dir))

            # download the files (curl -z)
            lFH = open(lOptions.download, "r")
            for lLine in lFH:
                lUrl = lLine.rstrip()
                lFilename = lUrl[lUrl.rfind('/') + 1:]
                lLocalFile = os.path.join(lDirDownload, lFilename)
#                if os.path.exists(lLocalFile):
#                    lStatBefore = os.stat(lLocalFile)
#                else:
#                    lStatBefore = None
                lContext.run_curl(lLocalFile, lUrl)
#                lStatAfter = os.stat(lLocalFile)
                # extract the files with yes to all queries to the wd
                # do this for all files in the working directory
#                if lOptions.forceextract or lStatBefore != lStatAfter:

        for lEntry in os.listdir(lDirDownload):
            lFileData = os.path.join(lDirDownload, lEntry)
            if os.path.isfile(lFileData) and \
                fnmatch.fnmatch(lEntry, "mtb*.exe"):
                    lContext.run_sevenzip(["x", "-y",
                        "-o" + lOptions.wd,
                        lFileData])

        lContext.generate_gmapsupp(lOptions.layout,
                lOptions.gmapsupp,
                lOptions.pattern)
    except LookupError, pExc:
        exit_exc(pExc)
    except NameError, pExc:
        exit_exc(pExc)
    except EOFError, pExc:
        exit_exc(pExc)
    except Exception, pExc:
        exit_exc(pExc)

    print("""
SUCCESS
gmapsupp.img generated

Please put gmapsupp.img into folder /garmin/ on your GPS memory \
(connect your GPS and choose mass storage mode) \
or write gmasupp.img directly to memory card into /garmin/ folder \
(for fast transfer put memory card into a cardreader) \
Backup any old gmapsupp.img that was placed there before if it \
exists already. \
Attention, if you want to have address search you have to use \
Mapsource to send maps to GPS.
""")


def exit_exc(pExc):
    print("Error: " + str(pExc))
    traceback.print_exc(file=sys.stdout)
    sys.exit(-1)

if __name__ == "__main__":
    main()
