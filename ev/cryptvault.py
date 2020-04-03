#!/usr/bin/env python3

import os
import kenl380.pylib as pylib

"""
The EncryptedVault class is configured to (hard-coded for now), to use things like:

local_dir = ~/vaults
dropbox_dir = ~/Dropbox/system/vaults

The caller just passes in the outer name, such as cv4gb, allowing the class to abstract
the local and remote versions. This also makes it so that a single object knows about both
the local and remote vault, and can easily provide more intelligent services to the user...

The way I am using Encrypted Vaults is by keeping a local copy on my desktop, and also
on my laptop, and then, whenever I make a change, I back it up to the Dropbox, so that
it can be updated on the other computer. This is clearly a design fraught with issues,
since there is no way to determine whether or not the remote computer did a RW mount and
forgot to backup, or perhaps forgot to dismount.

Things still left to do:

Clean up the mount logic for RW/RO modes.

Like aev, this script needs a bit of cleanup and commenting to help make things easier to
understand. Perhaps objectification, etc., just so it's more maintainable when I have to 
look at this in six months...

Implement the "last opened by" logic I've been brainstorming as a file in the Dropbox,
contained in the vault subfolder. That might at least catch some of the possible
out-of-sync cases, provided the network is always available...

    CEncryptedVaultVersion -> string    Version of the plist
    mounted -> boolean                  Is this volume currently mounted RW
    computer-name -> string             Computer name that has volume mounted
    needs-backup -> boolean             True when mounted RW, False after BACKUP
    ro-mounts -> array                  List of computers that have mounted RO

Partially implemented using plist; however, probably needs to be /vaults/VLTNAME.plist
instead of being in the vault directory, to avoid conflicts. Also, probably do not
want to record -read-only, right? and if read-write, FAIL the mount attempt, unless
it is a read-only attempt.

@TODO: Someday, would be nice to know if the Dropbox is in sync after a backup...
        or before doing a restore...
        
@TODO: Note that 'writable' in the hdiutil info command dict says if volume is RO...

Look at -plist, -puppetstrings options and how they will affect the output, making it
easier to parse...

@TODO: Should check to see if volume is mounted before doing any comparison checks...
        This could also apply to "looking" at the soon to exist flag file, to determine
        if it's possibly mounted somewhere else. And then this logic can be used when
        doing a mount or attach (not read-only) so you don't try to do something you
        shouldn't be doing...
        
@TODO: In the code, it seems clumbsy to have to call the writeplist() all the time.
        It also seems odd to have to always do the compare to see if it's me who has
        the volume mounted or not i.e. the checking of pylib.COMPUTER to ComputerName().
        This should probably be a built-in method to make the code more readable.

"""

def DefaultMessageHandler(msg):
    """ This will just eat messages sent to it. A good default for the message handler
        used by some of the class methods, in case the user doesn't care about them.""" 
    pass

# The class implementation for the exception handling in the underlying classes
class Error(Exception):
    """Base exception class for this module."""
    pass
    
class VaultError(Error):
    """Various exceptions raised by this module."""
    def __init__(self, errno, errmsg):
        self.errno = errno
        self.errmsg = errmsg
        
class C_EVDefaults:
    """This class abstracts the LOCAL and REMOTE locations on this computer"""
    def __init__(self):
        self.LocalPath = os.path.expanduser("~/vaults")
        self.RemotePath = os.path.expanduser("~/Dropbox/system/vaults")
        
    def LocalStorePath(self):
        return self.LocalPath
        
    def RemoteStorePath(self):
        return self.RemotePath
        
class C_EVPlist:
    """This object is used to abstract the plist that is used by the encrypted
    vault code to track state and detect certain bad things that might occur.
    It's far from perfect, but should work for what I need, at least for now..."""
    
    def __init__(self,vaultname):
    
        # @TODO: For now, store in LOCAL path until I get things worked out
        
        self.store = os.path.join(C_EVDefaults().LocalStorePath(),vaultname + ".plist")
        
        self.dirty = False
        self.LoadPlist()
    
    def GetPlist(self):
        return self.plist
        
    def LoadPlist(self):
        
        # @TODO: This thing needs error handling...
        if not os.path.isfile(self.store):
            # @TODO: Not sure if this is a good way to go. But this logic is needed for CREATE anyhow...
            default_plist = \
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + \
                "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n" + \
                "<plist version=\"1.0\">\n<dict>\n" + \
                "<key>CEncryptedVaultVersion</key>\n<string>1.0</string>\n" + \
                "<key>mounted</key>\n<false/>\n" + \
                "<key>computer-name</key>\n<string/>" + \
                "<key>needs-backup</key>\n<false/>\n" + \
                "<key>ro-mounts</key>\n<array/>\n" + \
                "</dict>\n</plist>\n"
                
            from plistlib import loads
    
            self.plist = loads(bytes(default_plist, encoding='UTF-8'))
            self.dirty = True   # if we created a new one, it's dirty... Doesn't work anyway
        else:
            from plistlib import load
            
            f = open(self.store,"rb")
    
            self.plist = load(f)
            
            f.close()
        
    def WritePlist(self):
        if self.dirty:
            from plistlib import writePlist
        
            writePlist(self.plist,self.store)
            
            self.dirty = False

    def Mounted(self):
        return self.plist['mounted']
        
    def SetMounted(self,mountflag):
        if self.plist['mounted'] != mountflag:
            self.plist['mounted'] = mountflag
            self.dirty = True
        
    def ComputerName(self):
        return self.plist['computer-name']
        
    def SetComputerName(self,name):
        if self.plist['computer-name'] != name:
            self.plist['computer-name'] = name
            self.dirty = True
        
    def NeedsBackup(self):
        return self.plist['needs-backup']
        
    def SetNeedsBackup(self,needs_backup):
        if self.plist['needs-backup'] != needs_backup:
            self.plist['needs-backup'] = needs_backup
            self.dirty = True
        

class C_VaultStore:
    """
    This class contains all of the methods for abstracting a disk image on the Mac,
    specifically a sparsebundle image. You give it a base path where the vaults are
    stored, and a name, and it builds up everything you need to manipulate it.
    
    @TODO: Add the ability to create a new vault from scratch.
    @TODO: Add the ability to mount vaults READ-ONLY
    """
    def __init__(self,path,vaultname):
        self.path = os.path.join(os.path.expanduser(path),vaultname)
        self.bundlepath = os.path.join(self.path,vaultname + '.sparsebundle')
        self.plist = os.path.join(self.bundlepath, 'Info.plist')
        self.bands = os.path.join(self.bundlepath, 'bands')
        
    def getPath(self):
        """Returns the vault path as a string"""
        return self.path
        
    def getBundlePath(self):
        """Returns the sparsebundle path as a string"""
        return self.bundlepath
        
    def getPList(self):
        """Returns the fully qualified Info.plist file for the sparsebundle as a string"""
        return self.plist
        
    def getBands(self):
        """Returns the fully qualified path to the sparsebundle bands as a string"""
        return self.bands
        
    def getBandDict(self):
        """Returns a dictionary containing all the individual band filenames as the
        key, and the current last modified time in seconds since epoch as the value.
        
        @TODO: This should be better thought out. A list of objects perhaps?"""
        return self.bandlist
        
    def load_bundle_bands(self):
        """Load the bands from the sparse bundle. This method will initialize the
        band dictionary (see getBandDict()). It isn't normally called, since as of now,
        the only time we need this is when we want to analyze to local and remote vaults
        to determine which is the most up to date. Currently returns 0, but that's kind
        of dumb."""
    
        bandlist = {}

        # make sure the path exists, otherwise bail now ...
        if not os.path.isdir('%s' % self.bands): return -1
    
        # go process all the directories in the versions folder
        for f in os.listdir(self.bands):
            curband = os.path.join(self.bands,f)
        
            # Only add files ...
            if os.path.isfile(curband):
                # convert to int May 2018 b/c I think Dropbox is truncating the
                # precision of the modify time to seconds when I transfer files
                # via rsync.
                bandlist[f] = int(os.path.getmtime(curband))
                
        self.bandlist = bandlist  # remember our band list
        
        # print("%s"%self.bands,bandlist)
    
        return 0


class C_EncryptedVault:
    """
    This class contains all the methods for abstracting the local/remote encrypted vault
    protocol that I made up so I could store private documents in a more secure manner,
    while still being able to leverage the Dropbox infrastructure for replication and
    backup.
    
    My protocol maintains two vaults: local and remote (Dropbox).
    
    This class has everything you need to manipulate the vaults, including:
    
    mount - mount the LOCAL vault
    dismount - dismount the LOCAL vault, if it's mounted
    backup - Make the LOCAL version the new REMOTE version. i.e. copy TO Dropbox
    restore - Make the REMOTE version the new LOCAL version. i.e. copy FROM Dropbox
    
    It currently contains an analyzeBands() method, which performs a high level
    analysis on the two vaults to help determine which is the most current, etc. This
    implementation still needs work.
    """
    def __init__(self,vaultname,message=DefaultMessageHandler):
        """Constructor for the C_EncryptedVault class. Initialize the
        variables that we need to have in order for the class to
        operate:
        
        vaultname - Name of the vault
        message - A function that is called with a string to print various status messages
        """
        
        evdefs = C_EVDefaults()
        self.vaultname = vaultname
        self.local = C_VaultStore(evdefs.LocalStorePath(),vaultname)
        self.remote = C_VaultStore(evdefs.RemoteStorePath(),vaultname)
        
        self.msgout = message
        self.valid = False
        
        if self.validate_vault_info(self.local): return
        
        if self.validate_vault_info(self.remote): return
        
        self.valid = True
        
    def validate_vault_info(self,which):
        """Validate vault information."""
        
        # make sure the path exists, otherwise bail now ...
        if not os.path.isdir(which.getPath()):
            raise VaultError(1, "The path you supplied isn't a directory '%s'" % which.getPath())
        
        if not os.path.isdir(which.getBundlePath()):
            raise VaultError(2, "The bundle path isn't a path '%s'" % which.getBundlePath())
        
        if not os.path.isfile(which.getPList()):
            raise VaultError(3, "This --> '%s', doesn't look like a sparsebundle to me..." % which.getPList())
            
        return 0
        
    def lookup(self,verb):
        """This will look up a method, but it's not implemented right, because it should
        make sure it exists first, and just be smarter about it.
        
        @TODO: Make this less dumb.
        """
        return getattr(self, verb)

    def localModifyTime(self):
        """Returns the last modified time of the LOCAL vault sparsebundle DIRECTORY.
        
        @TODO: I don't know that this is needed long term, now that we have analyzeBands()
        """
        if not self.valid: return -1
        
        return os.path.getmtime(self.local.getBands())
        
    def remoteModifyTime(self):
        """Returns the last modified time of the REMOTE vault sparsebundle DIRECTORY.
        
        @TODO: See localModifyTime @TODO
        """
        if not self.valid: return -1
        
        return os.path.getmtime(self.remote.getBands())
        
    def analyzeBands(self):
        """This performs an analysis on the bands in the two versions of the vault.
        
        @TODO: I need to make this much smarter, and probably use objects or some other
        type that makes more sense for this application.
        """
        self.local.load_bundle_bands()
        self.remote.load_bundle_bands()
        
        localbands = self.local.getBandDict()
        remotebands = self.remote.getBandDict()
        
        bandstate = {}
        
        bandstate['localcount'] = len(localbands)
        bandstate['remotecount'] = len(remotebands)
        bandstate['samecount'] = len(localbands) == len(remotebands)

        olderbands = newerbands = samebands = 0
        
        import time
        
        # print("%5s-%s" % (justname,time.strftime("%c",time.gmtime(bandlist[f]))))
                
        keylist = list(localbands.keys())
        keylist.sort()
        for item in keylist:
            if not item in remotebands:
                newerbands += 1
            elif localbands[item] == remotebands[item]:
                samebands += 1
            elif localbands[item] < remotebands[item]:
                olderbands += 1
                print("local[%s:%f] < remote[%s:%f]" % (item,localbands[item],item,remotebands[item]))
            elif localbands[item] > remotebands[item]:
                print("local[%s:%f] > remote[%s:%f]" % (item,localbands[item],item,remotebands[item]))
                newerbands += 1
                
        bandstate['olderbands'] = olderbands
        bandstate['newerbands'] = newerbands
        bandstate['samebands'] = samebands
        
        return bandstate
        
    def mount(self,ReadOnly=False):
        """Ok, let's go mount the vault."""
        
        if not self.valid:
            raise VaultError(4,'The mount() method was invoked while object was in an invalid state.')
            
        vault = C_EVPlist(self.vaultname)
        
        if( vault.Mounted() ):
            raise VaultError(5,'The vault is already mounted by %s' % vault.ComputerName())
        
        command = 'hdiutil attach %s' % self.local.getBundlePath()
        
        if( ReadOnly ): command += " -readonly"
            
        self.msgout('mounting encrypted vault: %s' % command)
        rc = os.system(command)

        if rc == 0:
            # Denote the object state.
            self.mounted = True
            #@TODO: Need to handle RO vs RW here properly...
            if not ReadOnly:
                # If we are mounting Read/Write, then set mounted and computer name
                self.msgout('setting mounted boolean and computer_name')
                vault.SetMounted(True)
                vault.SetComputerName(pylib.COMPUTER)
                vault.WritePlist()
            
        return rc

    def attach(self):
        return self.mount(True)     # Need a better way to do Read Only
        
    def backup(self):
        vault = C_EVPlist(self.vaultname)
        if vault.Mounted():
            self.msgout("Can't backup the volume while it is mounted by %s" % vault.ComputerName())
            return 1
            
        if not vault.NeedsBackup():
            self.msgout("According to my records, this vault doesn't need to be backed up...")
        
        if vault.ComputerName() != pylib.COMPUTER:
            self.msgout("I don't think you should backup your copy since you didn't have it mounted RW")
            return 2
            
        self.msgout("Backing up LOCAL (%s) to Dropbox (%s)..." % (self.local.getPath(),self.remote.getPath()))
        rc = os.system("rsync -va --delete \"%s/\" \"%s\"" % (self.local.getPath(), self.remote.getPath()))
        
        vault.SetNeedsBackup(False)
        vault.WritePlist()
        
        return rc
        
    def restore(self):
        vault = C_EVPlist(self.vaultname)
        if vault.Mounted():
            #@TODO: hdiutil mounted is the one that matters, but let's print this status for now ...
            self.msgout("FYI, doing restore of volume while it is mounted by %s" % vault.ComputerName())

        # Check to see if the volume on that sparse bundle is actually mounted here
        from ev.hdiinfo2 import MountedVolume
        
        volume = MountedVolume(self.local.getBundlePath())
        
        rc = 1
        if volume != None:
            self.msgout("Sorry, can't restore the volume while it's mounted locally ...")
        else:
            self.msgout("Restoring LOCAL (%s) from Dropbox (%s)..." % (self.local.getPath(),self.remote.getPath()))
            rc = os.system("rsync -va --delete \"%s/\" \"%s\"" % (self.remote.getPath(), self.local.getPath()))
            
        return rc
        
    def dismount(self):
        self.msgout("Dismounting %s..." % self.vaultname)
        
        if not self.valid:
            raise VaultError(4,'The mount() method was invoked while object was in an invalid state.')
        
        vault = C_EVPlist(self.vaultname)
        
        # @TODO: What do you check here? Do we care if the state of the plist file is wrong? Should we?
        #        What about checking to see if we had the thing mounted? Again, what do we do if the
        #        computer name is wrong? Is that so bad? We have it mounted now. Should we display a warning?
        if( not vault.Mounted() ):
            pass
            #raise VaultError(5,'The vault is already mounted by %s' % vault.computer_name())
        
        # Check to see if the volume on that sparse bundle is actually mounted here
        from ev.hdiinfo2 import MountedVolume
        
        volume = MountedVolume(self.local.getBundlePath())
        
        rc = 0
        if volume != None:
            # hdiutil reports the volume is currently mounted, so let's eject it
            command = 'hdiutil detach %s' % volume
            self.msgout('ejecting encrypted vault: %s' % command)
            rc = os.system(command)
            
        else:
        	self.msgout('no volume is currently mounted from %s' % self.local.getBundlePath())

        # This is out here, to handle the case where someone EJECTS the vault from
        # the computer with Finder, or if the computer reboots. Let's go ahead and
        # see if the computer and mounted flags in the plist file need cleanup...
        if rc == 0:
            # Denote the object state.
            self.mounted = False        # This seems dumb. Who looks at this?
            
            #@TODO: What about needs-backup? Here or above? or both?
            
            # Okay, it was mounted, so now we need to clean up the plist file
            
            if( vault.ComputerName() == pylib.COMPUTER and vault.Mounted()):
                # If the plist file says it was mounted by me, then let's clean up
                self.msgout('clearing mounted boolean and setting needs_backup...')
                vault.SetMounted(False)
                vault.SetNeedsBackup(True)  # This is right, right? IOW, don't backup until we DETACH
                vault.WritePlist()
                
            else:
                self.msgout("doesn't look like you had this mounted last -> %s..." % vault.ComputerName())

        else:
            self.msgout('no volume is currently mounted from %s' % self.local.getBundlePath())
                        
        return rc

    eject = dismount
    detach = dismount
    
    def about(self):
        if not self.valid:
            self.msgout("Not to be a negative nancy, but I see no reason to continue...")
            return 1
            
        import time
    
        self.msgout("LOCAL was last modified on %s" % time.asctime(time.localtime(self.localModifyTime())))
        self.msgout("Dropbox was last modified on %s" % time.asctime(time.localtime(self.remoteModifyTime())))
    
        if self.localModifyTime() > self.remoteModifyTime():
            self.msgout("LOCAL version was likely the most recently mounted version")
        elif self.localModifyTime() < self.remoteModifyTime():
            self.msgout("Dropbox version was likely the most recently mounted version")

        state = self.analyzeBands()
    
        if( state['samecount'] and (state['samebands'] == state['localcount']) ):
            self.msgout("It appears that the two vaults are identical...")
        
        elif( (state['olderbands'] + state['samebands']) == state['localcount'] ):
            self.msgout("It looks like the LOCAL vault is older than the Dropbox vault. Do a RESTORE.")
        
        elif( (state['newerbands'] + state['samebands']) == state['localcount'] ):
            self.msgout("It looks like the LOCAL vault is newer than the Dropbox vault. Do a BACKUP.")

        if( state['olderbands'] != 0 and state['newerbands'] != 0 ):
            self.msgout("The LOCAL vault has some older bands and some newer bands. This is BAD!")
        
        self.msgout("Hopefully, I haven't said anything contradictory or wrong!")
    
        import pprint
    
        self.msgout("Here is the full dictionary called 'state' in the code:")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(state)
        self.msgout("Go ahead, don't be scared ... make a decision.")
        
        return 0

if __name__ == "__main__":
    encvault = C_EVPlist("cv4gb")
    
    import pprint
    
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(encvault.GetPlist())
    
    #encvault.SETmounted(False)
    #encvault.SETcomputer_name("KENMP1")
    #encvault.SETneeds_backup(True)
    
    #encvault.WritePlist()

