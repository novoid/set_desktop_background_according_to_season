#!/opt/local/bin/python2.7
# -*- coding: utf-8 -*-
# Time-stamp: <2013-01-30 16:20:29 vk>
import re
import os


## TODO:
## * fix parts marked with «FIXXME»
## * possible for future: command line switch to get images from the opposite season only
## * possible for future: also match hours of day (+/- 1h; or: +/- that number of hours with a minimum of X matching images)

## a text file which will be filled (overwritten!) with
## the list of possible desktop background files:
FILE_WITH_IMAGEFILES = "/Users/vk/tmp/Tools/files_for_desktop_background.txt"

## minutes of idle time: a current idle time exceeding this value does result in an exit
## Reason: when I am not sitting infront of the computer, changing desktop images does not
## make any sense for me.
IDLE_TIME_BORDER = 20

## Do not re-generate the FILE_WITH_IMAGEFILES within this period of hours.
## Usually, the set of imagefiles does not change this quickly. So within the
## given period (in hours), re-use the previously generated file in order to
## spare some unnecessary load.
REGENERATE_FILE_WITH_IMAGEFILES_NOT_WITHIN = 24

## include files matching following regular expression
INCLUDE_FILES_REGEX = re.compile("([12]\d\d\d)-([012345]\d)-([012345]\d).*(specialL|\(desktoppicture\)|\(dp\)).*\.(jpg|jpeg)$")

## exclude all files located in folders matching following regular expression
EXCLUDE_FOLDERS_REGEX = re.compile(".*(foobar|Library).*")

## list of starting folders to query for matching files:
home_folder = os.path.expanduser("~")
LIST_OF_PATHS_TO_QUERY = [
    os.path.join(home_folder, 'archive/events_memories'),
    os.path.join(home_folder, 'art'),
    ]


## ===================================================================== ##
##  You might not want to modify anything below this line if you do not  ##
##  know, what you are doing :-)                                         ##
## ===================================================================== ##

## NOTE: in case of issues, check iCalendar files using: http://icalvalid.cloudapp.net/

import sys
import time
import datetime
import logging
from subprocess import *
from optparse import OptionParser
import fnmatch
from random import choice
from appscript import *

## debugging:   for setting a breakpoint:  pdb.set_trace()
#import pdb

PROG_VERSION_NUMBER = u"0.1"
PROG_VERSION_DATE = u"2013-01-27"
INVOCATION_TIME = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())



USAGE = u"\n\
    " + sys.argv[0] + u"\n\
\n\
This script sets the OS X 10.5 desktop background\n\
to a randomly chosen image which was taken in a similar\n\
season to the current one.\n\
\n\
Please refer to README.org for further details.\n\
\n\
https://github.com/novoid/set_desktop_background_according_to_season\n\
\n\
:copyright: (c) 2013 by Karl Voit <tools@Karl-Voit.at>\n\
:license: GPL v3 or any later version\n\
:bugreports: <tools@Karl-Voit.at>\n\
:version: "+PROG_VERSION_NUMBER+" from "+PROG_VERSION_DATE+"\n"

parser = OptionParser(usage=USAGE)

parser.add_option("-i", "--ignoreidle", dest="ignoreidle", action="store_true",
                  help="ignore idle time and change background in any case")

parser.add_option("-f", "--force", dest="force", action="store_true",
                  help="run everything and change background regardless of idle time or age of file list")

parser.add_option("-v", "--verbose", dest="verbose", action="store_true",
                  help="enable verbose mode")

parser.add_option("-q", "--quiet", dest="quiet", action="store_true",
                  help="enable quiet mode")

parser.add_option("--version", dest="version", action="store_true",
                  help="display version and exit")

(options, args) = parser.parse_args()


def handle_logging():
    """Log handling and configuration"""

    if options.verbose:
        FORMAT = "%(levelname)-8s %(asctime)-15s %(message)s"
        logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    elif options.quiet:
        FORMAT = "%(levelname)-8s %(message)s"
        logging.basicConfig(level=logging.ERROR, format=FORMAT)
    else:
        FORMAT = "%(levelname)-8s %(message)s"
        logging.basicConfig(level=logging.INFO, format=FORMAT)


def error_exit(errorcode, text):
    """exits with return value of errorcode and prints to stderr"""

    sys.stdout.flush()
    logging.error(text)

    sys.exit(errorcode)


def get_idle_seconds():
    '''Return idle time of OS X 10.5 in seconds'''
    ## stolen from: http://stackoverflow.com/questions/2425087/testing-for-inactivity-in-python-on-mac

    # Get the output from
    # ioreg -c IOHIDSystem
    output  = Popen(["ioreg", "-c", "IOHIDSystem"], stdout=PIPE).communicate()[0]
    lines = output.split('\n')

    raw_line = ''
    for line in lines:
        if line.find('HIDIdleTime') > 0:
            raw_line = line
            break

    nano_seconds = long(raw_line.split('=')[-1])
    seconds = nano_seconds/1000000000
    logging.debug("idle time is %s seconds (%s ns)" % (seconds, nano_seconds))
    return seconds


def exit_if_idle_time_is_too_large():
    """exit with errorcode 0 if system idle time is below the
    threshold minutes stored in IDLE_TIME_BORDER"""

    currentidleminutes = get_idle_seconds()/60

    if currentidleminutes > int(IDLE_TIME_BORDER):
        logging.debug("idle time (%s minutes) is too large for me; doing nothing." % \
                          str(currentidleminutes))
        sys.exit(0)

    return True


def delete_file_if_found(filename):
    """remove file from file system, if it exists"""

    if os.path.exists(filename):
        logging.debug("deleting file \"%s\"." % filename)
        os.remove(filename)


def query_folder(folder, list_of_files_found):
    """Walk the folder and its sub-folders and collect files matching
    INCLUDE_FILES_REGEX whose folder do not match
    EXCLUDE_FOLDERS_REGEX."""

    ## http://stackoverflow.com/questions/5141437/filtering-os-walk-dirs-and-files

    for root, dirs, files in os.walk(folder):

        # exclude dirs
        dirs[:] = [os.path.join(root, d) for d in dirs]
        dirs[:] = [d for d in dirs if not re.match(EXCLUDE_FOLDERS_REGEX, d)]

        # exclude/include files
        files = [f for f in files if re.match(INCLUDE_FILES_REGEX, f)]
        files = [os.path.join(root, f) for f in files]

        for fname in files:
            list_of_files_found.append(fname)

    return list_of_files_found


def regenerate_file_list_with_desktop_background_files(FILE_WITH_IMAGEFILES):
    """re-generate file list with desktop background files by
    traversing all sub-folders of LIST_OF_PATHS_TO_QUERY."""

    if os.path.exists(FILE_WITH_IMAGEFILES):
        file_with_imagefiles_mtime = os.path.getmtime(FILE_WITH_IMAGEFILES)
        unix_epoch_now = time.time()
        difference_in_hours = int((unix_epoch_now - file_with_imagefiles_mtime)/(60*60))

        logging.debug("FILE_WITH_IMAGEFILES is %s hours old" % str(difference_in_hours))

        if not options.force and REGENERATE_FILE_WITH_IMAGEFILES_NOT_WITHIN > difference_in_hours:
            logging.debug("difference_in_hours is too small, re-using old file.")
            ## use the same file again, if difference in hours is too small
            return

        delete_file_if_found(FILE_WITH_IMAGEFILES)

    logging.info("re-generating \"%s\" ..." % FILE_WITH_IMAGEFILES)

    list_of_files_found = []

    for folder in LIST_OF_PATHS_TO_QUERY:
        found_files_before = len(list_of_files_found)
        list_of_files_found = query_folder(folder, list_of_files_found)
        logging.debug("found files before [%s]; len of list [%s] after folder [%s]" % \
                          (str(found_files_before), str(len(list_of_files_found)), folder))
        logging.info("found %s matching files in \"%s\"" % \
                          (str(len(list_of_files_found) - found_files_before),
                           str(folder))
                      )

    logging.info("found %s matching files in total" % str(len(list_of_files_found)))

    with open(FILE_WITH_IMAGEFILES, 'w') as output:
        for line in list_of_files_found:
            output.write(line + '\n')


def check_if_image_month_matches_season_criteria(current_month, image_month):
    """Returns True if the month of the image is the current one or
    the one after the current one."""

    ## previous criteria: image_month is within previous month to next month:
    ##difference_in_months = int(components.group(2)) - int(current_month)
    ##difference_in_months<2 or difference_in_months==11:
    ## ... BUT: xmas-photos in Jannuary seem odd to me

    if current_month==12:
        next_month = 1
    else:
        next_month = current_month+1

    return( image_month==current_month or image_month==next_month )


def parse_and_filter_desktop_background_files():
    """read in FILE_WITH_IMAGEFILES and search for matching files
    according to current_month."""

    current_month = datetime.datetime.now().strftime("%m")
    #logging.debug("current month: [%s]" % current_month)

    all_image_files = []
    count=0

    with open(FILE_WITH_IMAGEFILES, 'r') as file_with_imagefiles:

        for line in file_with_imagefiles:

            count +=1
            filename = os.path.basename(line)
            components = re.match(INCLUDE_FILES_REGEX, filename)

            if not components:
                error_exit(10,"ERROR: This should not happen: filename \"" + \
                               filename + \
                               "\ is not matched by INCLUDE_FILES_REGEX!")

            image_month = components.group(2)
            if check_if_image_month_matches_season_criteria(int(current_month), int(image_month))
                all_image_files.append(line)

    logging.debug("found %s seasonal matching files (within %s image files)" % (
            str(len(all_image_files)),
            str(count)
            ))

    return all_image_files


def set_desktop_backgrounds(file):
    """Set the OS X 10.5 desktop background image using the file
    given."""

    logging.info("setting desktop backgrounds to \"%s\"" % file.strip())
    system_events = app('System Events')
    desktops = system_events.desktops.display_name.get()
    for current_desktop in desktops:
        desk = system_events.desktops[its.display_name == current_desktop]
        desk.picture.set(mactypes.File(file.strip()))


def main():
    """Main function"""

    if options.version:
        print os.path.basename(sys.argv[0]) + " version " + PROG_VERSION_NUMBER + \
            " from " + PROG_VERSION_DATE
        sys.exit(0)

    handle_logging()

    if options.verbose and options.quiet:
        error_exit(1,"Options \"--verbose\" and \"--quiet\" found. " + \
                       "This does not make any sense, you silly fool :-)")

    ## 1. get system idle time
    if not options.force and not options.ignoreidle:
        exit_if_idle_time_is_too_large()
    ## 2. if idle time < IDLE_TIME_BORDER minutes continue (else exit)

    ## 3. re-generate files_for_desktop_background.txt
    regenerate_file_list_with_desktop_background_files(FILE_WITH_IMAGEFILES)

      ## 4. determine current month
  ## 5. read-in files_for_desktop_background.txt and parse for ISO
    ##    timestamps in filenames
    all_image_files = parse_and_filter_desktop_background_files()

    ## 6. randomly choose a file with matching month from the list
        ## FIXXME: prevent same file picked twice without any other file in between?
    chosen_image = choice(all_image_files)

    ## 7. set this file as new desktop background
    set_desktop_backgrounds(chosen_image)

    logging.info("successfully finished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:

        logging.info("Received KeyboardInterrupt")

## END OF FILE #################################################################

#end
