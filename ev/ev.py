#!/usr/bin/env python3

import os
import sys
import string

import kenl380.pylib as pylib

def context(varfile=None):
    """returns the context object for this script."""

    try:
        myself = __file__
    except NameError:
        myself = sys.argv[0]

    return pylib.context(myself,varfile)

me = context('ev')

def message(msgstr): print ('%s: %s' % (me.alias(),msgstr))

from ev.cryptvault import C_EncryptedVault, VaultError

def usage():
	message("invalid usage")
	sys.exit(1)

def ev_entry():
    from sys import argv

    message(me.pyVersionStr())
    # assume we have no arguments, but if we do, pass them along
    args = []
    if len(sys.argv) > 1: args = sys.argv[1:]
    
    if len(args) < 1: usage()

    try:
        encvlt = C_EncryptedVault(args[0],message)
    except VaultError as ve:
        message("Vault class threw exception %d:%s" % (ve.errno, ve.errmsg))
        return(1)
    
    if not encvlt.valid:
        message("Not to be a negative nancy, but I see no reason to continue...")
        return(1)

    verb = args[1].lower()
    
    if not hasattr(encvlt,verb):
        message("Could be me, but I don't see any object methods named '%s' on the encvlt variable" % verb)
        return(1)
        
    try:
        message('%s returned %d' % (verb, encvlt.lookup(verb)()))
    except VaultError as ve:
        message("Vault class threw exception %d:%s" % (ve.errno, ve.errmsg))
        return(1)
    
    """answer = sys.stdin.readline().strip()
    
    if answer.lower() in ["yes", "y", "si"]:
        message("You entered YES")
        clpsync(True)
    else:
        message("You did not enter YES, you entered %s" % answer)"""
        
    # invoke the execute method on the object, it takes care of all else
    return(1)
    
if __name__ == '__main__':
    from sys import exit
    exit(ev_entry())
