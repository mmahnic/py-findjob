#!/usr/bin/env python
# vim:set fileencoding=utf-8 sw=4 ts=8 et:vim
# Author:  Marko Mahnič
# Created: mar 2007 
#
# This classes were created for a bakckup system that incrementally adds
# files to ZIP archives. It uses external programs find and zip to do
# the work. The classes below are mostly used to prepare the parameters
# for the external programs and to run them.

import string
import datetime
import subprocess as subp
import shlex, os

PSEP = ":"
MAXAGE_FALLBACK = 7
def _pathSplit(pathdef):
    if type(pathdef) == type(""): pathdef = [pathdef]
    parts = []
    for pd in pathdef:
        for line in pd.split("\n"):
            for m in line.split(PSEP):
                m = m.strip()
                if m != "": parts.append(m)
    return parts

class IncrementalInfo:
    def __init__(self):
        self.incremental = False
        self.referenceTime = None
        self._referenceFile = None
        self.maxAgeDays = MAXAGE_FALLBACK

    @property
    def referenceFile(self):
        if self._referenceFile == None: return None
        if not os.path.exists(self._referenceFile): return None
        return self._referenceFile

    def getArchiveSuffix(self):
        if not self.incremental: return ""
        age = self.maxAgeDays
        if age == None: age = MAXAGE_FALLBACK
        return "_i%d" % age
        # all incremental filenames must have maxAgeDays appended,
        # otherwise findReferenceFile doesn't work properly
        #if self.referenceTime != None: return "_i"
        #if self.referenceFile != None: return "_i"

class FindJobBuilder(object):
    def __init__(self, rootdir="."):
        self._rootdir = rootdir.replace(' ', r"\ ")
        self._includeFiles = []
        self._excludeDirs = []
        self._excludeFiles = []
        self._mtimeNewer = None
        self._ignorecase = False
        self._followLinks = False
        self.clear()
        
    def clear(self):
        self._includeFiles = []
        self._excludeDirs = []
        self._excludeFlies = []

    def setRoot(self, rootdir):
        self._rootdir = rootdir.replace(' ', r"\ ")

    def setIgnorecase(self, ignorecase=True):
        self._ignorecase = ignorecase

    def setFollowLinks(self, follow=True):
        self._followLinks = follow

    def _processFileList(self, masklist, ignorecase=None):
        if ignorecase == None: ignorecase = self._ignorecase
        def procFile(m):
            if m.find('/') >= 0: test = "wholename"
            else: test = "name"
            if ignorecase: test = "i" + test
            return '-%s "%s"' % (test, m)
        tests = [procFile(m) for m in _pathSplit(masklist)]
        return tests

    def includeFiles(self, masklist, ignorecase=None):
        tests = self._processFileList(masklist, ignorecase)
        self._includeFiles.extend(tests)

    def skipFiles(self, masklist, ignorecase=None):
        tests = self._processFileList(masklist, ignorecase)
        self._excludeFiles.extend(tests)

    def _processDirList(self, masklist, ignorecase=None):
        if ignorecase == None: ignorecase = self._ignorecase
        def procDir(m):
            if m[0] not in ['*', '/', '?']: m = '"%s/%s"' % (self._rootdir, m)
            m = m.replace(' ', r"\ ")
            if ignorecase: test = "iwholename"
            else: test = "wholename"
            return '-%s "%s"' % (test, m)
        tests = [procDir(m) for m in _pathSplit(masklist)]
        return tests

    def skipDirs(self, masklist, ignorecase=None):
        tests = self._processDirList(masklist, ignorecase)
        self._excludeDirs.extend(tests)

    def setMaxAge(self, numdays):
        if numdays == None: self._mtimeNewer = None
        # else: self._mtimeNewer = "-mtime %d" % numdays
        else: self.setNewerTime(datetime.datetime.now() - datetime.timedelta(days=numdays, hours=1))

    def setNewer(self, filename):
        if numdays == None: self._mtimeNewer = None
        else: self._mtimeNewer = ['-newer',  '"%s"' % filename]

    def setNewerTime(self, mtime):
        if mtime == None: self._mtimeNewer = None
        else: self._mtimeNewer = ['-newermt',  '"%s"' % mtime.strftime("%Y-%m-%d %H:%M:%S")]

    def setIncrementalParams(self, incrementalInfo):
        if not incrementalInfo.incremental:
            self.setMaxAge(None)
        elif incrementalInfo.referenceTime != None:
            self.setNewerTime(incrementalInfo.referenceTime)
        elif incrementalInfo.referenceFile != None:
            self.setNewer(incrementalInfo.referenceFile)
        else:
            if incrementalInfo.maxAgeDays == None: incrementalInfo.maxAgeDays = MAXAGE_FALLBACK
            self.setMaxAge(incrementalInfo.maxAgeDays)

    # FORM:
    # find -H rootdir ( skip_dirs ) -prune -o \
    #      ( -not -type d -a ( incl_files ) -a -not ( excl_files ) ) -print
    def getFindCommand(self):
        links = '-L' if self._followLinks else '-H'
        params = ["find %s '%s'" % (links, self._rootdir)]
        if len(self._excludeDirs):
            list = string.join(self._excludeDirs, " -o ")
            params.append(r"\( %s \) -prune -o" % list)
        params.append(r"\( -not -type d")
        if self._mtimeNewer != None:
            params.extend(["-a"] + self._mtimeNewer)
        if len(self._includeFiles) > 0 or len(self._excludeFiles) > 0:
            if len(self._includeFiles) > 0:
                list = string.join(self._includeFiles, " -o ")
                params.append(r"-a \( %s \)" % list)
            if len(self._excludeFiles) > 0:
                list = string.join(self._excludeFiles, " -o ")
                params.append(r"-a -not \( %s \)" % list)
        params.append(r"\) -print")
        return string.join (params, " ")

    def run(self):
        pf = subp.Popen(shlex.split(self.getFindCommand()), stdout=subp.PIPE)
        (out, err) = pf.communicate()
        return (out.split("\n"), err)



# Searches the filesystem under jobBuilder.rootdir to find .backupsettings
# and reads the settings
class BackupOptionReader:
    def __init__(self):
        self.filename = ".backupsettings"
        self.clear()

    def clear(self):
        self.skipdirs = ""
        self.skipfiles = ""

    def readOptions(self, jobBuilder):
        self.settings = {}
        JB = FindJobBuilder(jobBuilder._rootdir)
        JB._excludeDirs = [d for d in jobBuilder._excludeDirs]
        JB.includeFiles(self.filename)
        pf = subp.Popen(shlex.split(JB.getFindCommand()), stdout=subp.PIPE)
        (out, err) = pf.communicate()
        for bs in out.split("\n"):
            if bs.strip() == "": continue
            dirname = os.path.dirname(bs)
            for line in open(bs, "r").readlines():
                if line.startswith("skipdirs="):
                    items = _pathSplit(line[9:])
                    items = [os.path.join(dirname, i) for i in items]
                    self.skipdirs += (":".join(items)) + "\n"
                if line.startswith("skipfiles="):
                    items = _pathSplit(line[10:])
                    items = [os.path.join(dirname, i) for i in items]
                    self.skipfiles += (":".join(items)) + "\n"
        #print self.skipdirs
        #print self.skipfiles


class ArchiveFileManager(object):
    def __init__(self, archiveRootDir=None, jobname=None):
        self._now = datetime.datetime.now()
        self._rootdir = archiveRootDir
        self._jobname = jobname
        self._referenceFileModes = "w"
        self._backupmode = "w"
        self.incMode = IncrementalInfo()
        self._logfile = None
        self.ext = ".zip"

    def setRootDir(self, archiveRootDir):
        self._closeLogfile()
        self._rootdir = archiveRootDir

    def _setJobName(self, jobname):
       self._closeLogfile()
       self._jobname = jobname

    #def setIncremental(self, incremental=True):
    #    self._closeLogfile()
    #    self.incMode.incremental = incremental

    # @param referenceFileModes - which files to try to use as a time-reference file
    #   "XYZ" - list of modes to check, X,Y,Z in [h, d, w, m]
    #   * - same as mode (default)
    #   None - don't use a reference file, use mtime
    def _setBackupMode(self, mode, incremental=True, referenceFileModes="*", mtime=None):
        self._closeLogfile()
        assert mode in ["h", "d", "w", "m"]
        if referenceFileModes == "*": referenceFileModes = mode
        self._backupmode = mode
        self._referenceFileModes = referenceFileModes
        self.incMode.incremental = incremental
        self.incMode._referenceFile = None
        if mtime == None:
           if mode == "h" or mode == "d": mtime = 1
           elif mode == "w": mtime = 7
           else: mtime = 31
        self.incMode.maxAgeDays = mtime

    def configureBackup(self, jobname, mode, incremental=True, referenceFileModes="*", mtime=None, selector=None):
        self._setJobName(jobname)
        self._setBackupMode(mode, incremental, referenceFileModes, mtime) # default
        if selector != None: selector.selectBackupMode(self)

    # works for current year only
    def findReferenceFile(self):
        if self._referenceFileModes == None: return
        os.stat_float_times(True)
        thisfile = self.getArchivePath() # not exactly! the real path depends on results of findReferenceFile
        maxtime = self._now
        if os.path.exists(thisfile):
            st = os.stat(thisfile)
            maxtime = datetime.datetime.fromtimestamp(st.st_mtime)
        besttime = None
        bestfile = None
        for mode in self._referenceFileModes:
            modedir = self._getArchiveDir(self._rootdir, self._now, mode)
            basename = self._getArchiveBaseName(self._now, mode)
            for fn in os.listdir(modedir):
                if not fn.endswith(self.ext): continue
                if not fn.startswith(basename): continue
                fnfull = os.path.join(modedir, fn)
                if mode == self._backupmode and thisfile == fnfull: continue
                # print "Checking", fnfull
                st = os.stat(fnfull)
                ftime = datetime.datetime.fromtimestamp(st.st_mtime)
                if ftime >= maxtime: continue
                if besttime == None or ftime > besttime:
                    besttime = ftime
                    bestfile = fnfull
        if besttime == None:
            self.incMode.referenceTime = None
            self.incMode.referenceFile= None
        else:
            self.incMode.referenceTime = besttime - datetime.timedelta(hours=1) # for safety
            self.incMode.referenceFile = bestfile
            self.appendLog("  Reference: %s %s" % (self.incMode.referenceTime, os.path.basename(bestfile)))

        return

    def _getArchiveDir(self, root, date, mode):
        return "%s/%s/%s" % (root, date.strftime("%Y"), mode)

    def getArchiveDir(self):
        return self._getArchiveDir(self._rootdir, self._now, self._backupmode)

    def _getArchiveBaseName(self, date, mode):
        if self._backupmode == "h": dnm = self._now.strftime("%Y%m%dh")
        elif self._backupmode == "d": dnm = self._now.strftime("%Y%md")
        elif self._backupmode == "w": dnm = self._now.strftime("%Yw")
        elif self._backupmode == "m": dnm = self._now.strftime("%Ym")
        return "%s%s" % (self._jobname, dnm)

    def getArchiveName(self):
        if self._backupmode == "h": dnm = self._now.strftime("%Y%m%dh%H%M")
        elif self._backupmode == "d": dnm = self._now.strftime("%Y%md%d")
        elif self._backupmode == "w": dnm = self._now.strftime("%Yw%W")
        elif self._backupmode == "m": dnm = self._now.strftime("%Ym%m")
        return "%s%s%s" % (self._jobname, dnm, self.incMode.getArchiveSuffix())

    def getArchivePath(self):
        return "%s/%s%s" % (self.getArchiveDir(), self.getArchiveName(), self.ext)

    def getLogDir(self):
        return "%s/%s" % (self._rootdir, "logs")

    def getLogfilePath(self):
        fname = self._now.strftime("backup%Y.log")
        return "%s/%s/%s" % (self._rootdir, "logs", fname) # self._jobname)

    def _closeLogfile(self):
        if self._logfile:
            self._logfile.close()
            self._logfile = None

    def _getLogfile(self):
        if self._logfile != None: return self._logfile
        if not os.path.exists(self.getLogDir()):
            os.makedirs(self.getLogDir())
        self._logfile = open(self.getLogfilePath(), "a")
        return self._logfile

    def appendLog(self, text):
        if text == "*job*": text = "%s %s" % (self.getArchiveName(), self._rootdir)
        if text == "*end*": text = "END\n----------------"
        now = datetime.datetime.now()
        tmst = now.strftime("%a %Y-%m-%d %H:%M:%S")
        f = self._getLogfile()
        f.write("%s: %s\n" % (tmst, text))
        self._closeLogfile()

    def findAndZip(self, finder):
        if not os.path.exists(self.getArchiveDir()):
            os.makedirs(self.getArchiveDir())

        now = datetime.datetime.now()
        self.appendLog("*job*")

        BR = BackupOptionReader()
        BR.readOptions(finder)
        finder.skipDirs(BR.skipdirs)
        finder.skipFiles(BR.skipfiles)
        self.appendLog("  Settings read in: %s" % (datetime.datetime.now() - now))

        now = datetime.datetime.now()
        if self.incMode.incremental: self.findReferenceFile()
        finder.setIncrementalParams(self.incMode)
        finder.skipDirs(self._rootdir)
        print finder.getFindCommand()
        try:
            pf = subp.Popen(shlex.split(finder.getFindCommand()), stdout=subp.PIPE)
            pz = subp.call(["zip", "-u", self.getArchivePath(), "-@"], stdin=pf.stdout)
        except Exception as e:
            self.appendLog("  *** Error: %s" % e)

        self.appendLog("  Archive updated in: %s" % (datetime.datetime.now() - now))

    def runBackups(self, listFnBackup):
        self.appendLog( "Backup started -----")
        now = datetime.datetime.now()
     
        for backup in listFnBackup: backup(self)
     
        now = datetime.datetime.now() - now
        self.appendLog("Total duration: %s" % now)
        self.appendLog("END\n" + ("-" * 28))


# a slightly configurable backup mode selector
#   * full or incremental backup, depending on file existence
#   * time delta (hour, day, week, month), depending on file existence
class BackupModeSelector:
    def __init__(self):
        # Try the modes in the following order until a mode with no existing backup is found
        # if all modes have a backup, the last mode is used
        # if maxAge [days] is specified for a mode, perform backup for that mode even if
        # a backup exists, but is older than the age specified
        self.modes = "mw"
        self.maxAges = {"m": 7, "w": 3, "d": 3, "h": 0}

        # When incremental type is selected, switch to full type on the specified weeks
        # and set the backup mode to the specified mode
        self.full_weeks = [4, 17, 33, 50]
        self.full_mode = "m"

    def selectBackupMode(self, arch):
        (year, week, weekday) = arch._now.isocalendar()

        has_incremental = arch.incMode.incremental
        if has_incremental:
            # On certain weeks perform a full backup if it doesn't exist
            if week in self.full_weeks:
                arch._setBackupMode(self.full_mode, incremental=False)
                afn = arch.getArchivePath()
                if not os.path.exists(afn):
                    arch.appendLog("%s: Full backup auto-selected" % arch.getArchiveName())
                    return

        # if backup for month exists, do a weekly backup
        # if backup for week exists, do a daily backup, etc.
        for mode in self.modes[:-1]:
            arch._setBackupMode(mode, incremental=has_incremental)
            afn = arch.getArchivePath()
            reason = "new"
            use_this = not os.path.exists(afn)
            if not use_this:
                try:
                    mage = self.maxAges[mode]
                    if mage != None:
                        mage = arch._now - datetime.timedelta(days=mage)
                        st = os.stat(afn)
                        ftime = datetime.datetime.fromtimestamp(st.st_mtime)
                        if ftime < mage:
                            use_this = True
                            reason = "age"
                except: pass
            if use_this:
                arch.appendLog("%s: mode auto-selected (reason: %s)" % (arch.getArchiveName(), reason))
                return

        arch._setBackupMode(self.modes[-1], incremental=has_incremental)


if __name__ == "__main__":
    pass
    #TEMPDIRS="*/temp:*/Temp:*/TEMP:*/tmp:*/Tmp:*/TMP"
    #BACKUPFILES="*.bak:*.~*:*.*~"
    #VCBUILDDIRS="*/Release:*/Debug"
    #BUILDDIRS="*/BUILD:*/Build:*/build"

    #now = datetime.datetime.now()
    #JB = FindJobBuilder("/home/mmarko")
    #JB.setIgnorecase()
    #JB.includeFiles("*:.*")
    #JB.skipFiles(BACKUPFILES)
    #JB.skipFiles("*/bin/*.o:*/bin/*.obj")
    #JB.skipDirs(TEMPDIRS)
    #JB.skipDirs(VCBUILDDIRS)
    
    #AR = ArchiveFileManager("/home/mmarko/Documents/.backup", "profile")
    #AR.setBackupMode("w", incremental=True)

    #findAndZip(JB, AR)

    #now = datetime.datetime.now() - now
    #AR.appendLog("Total duration: %s" % now)
    #AR.appendLog("*end*")

