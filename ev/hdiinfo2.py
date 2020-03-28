#!/usr/bin/env python3

"""
This module uses HDIUTIL to get info on mounted disk images. It will return the
PList of the hdiutil info verb so it can be parsed, and there is also a method
that looks up and returns the mount point of an Apple_HFS volume for the specified
sparse image bundle.
"""

import os
import sys

def GetHDIInfo():
    """Returns the output from HDI INFO as a PList Dictionary
    
    Returns:
        None - If no hdiutil disk images are mounted
        []   - Array (list) of each line of output ready for parsing"""

    list = []

    from subprocess import getoutput

    listCommand = 'hdiutil info -plist'
    
    out = getoutput(listCommand)
    from plistlib import loads
    
    plist = loads(bytes(out,encoding='UTF-8'))

    return plist
    
def MountedVolume(bundle):
    """
    Look to see if the specified bundle has an attached Apple_HFS volume. If so,
    return the mount-point, so it can be ejected (or printed, if that's what you
    want to do.
    
    Returns: String - The volume mount-point suitable for hdiutil detach
             None - Doesn't look like the volume is mounted.
    """

    plist = GetHDIInfo()
    
    # plist['images'] will be empty if no disk images are mounted
    for image in plist['images']:
    
        # Haven't tested enough to know if 'image-path' is always there
        if 'image-path' not in image:
            continue
            
        # Look to see if the image is the one we are looking for
        if image['image-path'] != bundle:
            continue

        # Each image can have multiple file systems and mounts. In the case
        # of our Encrypted Images, we are looking only for Apple_HFS file systems.
        
        for entity in image['system-entities']:
            if entity['content-hint'] in "Apple_HFS":
                # Return the mount point of the image so it can be ejected/unmounted
                # Haven't tested enough to know if there can be multiple file systems
                # in a single bundle, but I don't think so...
                return entity['mount-point']

    return None                

if __name__ == "__main__":
    plist = GetHDIInfo()
    
    import pprint
    
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(plist)

    print(MountedVolume("/Users/ken/vaults/cv4gb/cv4gb.sparsebundle"))
    