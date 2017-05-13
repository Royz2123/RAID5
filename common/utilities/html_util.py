# -*- coding: utf-8 -*-
import errno
import logging
import os
import select
import time
import traceback

from common.utilities import constants
from common.utilities import util

ALIGNMENTS = {
    True : "left-volume-disk-pic",
    False : "right-volume-disk-pic",
}
IMAGES = {
    constants.OFFLINE : "offline_disk1.png",
    constants.ONLINE : "online_disk.png",
    constants.REBUILD : "rebuild_disk.gif",
}
VOLUME_STATE = {
    0 : "All good",
    1 : "No more disconnecting please!",
    2 : "Inactive!!",
}

#HTML OBJECT CREATOR FUNCTIONS:

def html_progress_bar(disk, volume_UUID):
    rebuild_prcntg = disk["cache"].get_rebuild_percentage()
    if rebuild_prcntg < 0:
        return "Rebuilding first from scratch..."
    return (
        "Rebuilding progress:<br><progress value='%s' max='100'></progress>"
        % (
            rebuild_prcntg
        )
    )

def disconnect_form(disk, volume_UUID):
    return (
        '<form action="/disconnect" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disk_UUID" value=%s>'
        + '<input type="hidden" name="volume_UUID" value=%s>'
        + '<input type="submit" value="Disconnect">'
        + '</form>'
    ) % (
        disk["disk_UUID"],
        volume_UUID,
    )

def connect_form(disk, volume_UUID):
    return (
        '<form action="/connect" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disk_UUID" value=%s>'
        + '<input type="hidden" name="volume_UUID" value=%s>'
        + '<input type="submit" value="Connect">'
        + '</form>'
    ) % (
        disk["disk_UUID"],
        volume_UUID,
    )


HTML_OBJECTS = {
    constants.OFFLINE : connect_form,
    constants.ONLINE : disconnect_form,
    constants.REBUILD : html_progress_bar,
}


def create_html_page(
    content,
    header=constants.HTML_DEFAULT_HEADER,
    refresh=None,
    redirect_url="",
):
    refresh_header = ""
    if refresh is not None:
        refresh_header = (
            "<meta http-equiv='refresh' content='%s%s'>"
            % (
                refresh,
                "; %s" % (redirect_url * (redirect_url!=""))
            )
        )

    return (
        (
            "<HTML><HEAD>%s%s%s<TITLE>%s</TITLE></HEAD>"
            + "<BODY>%s<div class='%s'>%s</div></BODY></HTML>"
        )% (
            create_style_link(),
            create_style_link(
                "http://fonts.googleapis.com/css?family=Hind+Madurai"
            ),
            refresh_header,
            header,
            constants.HTML_TOP_BAR_CODE,
            constants.DEFAULT_CONTENT_SPACE,
            content
        )
    )

def create_style_link(
    sheet=constants.DEFAULT_STYLE_SHEET
):
    return (
        "<link rel='stylesheet' type='text/css' href=%s>"  % (
            sheet
        )
    )


def create_disks_list(available_disks, volumes):
    disk_list = ""

    #First handle the initialized_volumes
    for volume_UUID, volume in util.initialized_volumes(volumes).items():
        #General volume info:
        #Calculate some stats...
        online_volume_disks = len(
            [disk for disk_UUID, disk in volume["disks"].items()
            if disk["state"] == constants.ONLINE]
        )
        total_disks = len(volume["disks"])
        bad_disks = total_disks - online_volume_disks

        #update the disk_list
        disk_list += (
            (
                "<h2>Volume%s</h2>"
                + "<h3>Volume UUID: %s</h3>"
                + "<h3>Disks Online: %s/%s, Volume State: %s</h3> "
            ) % (
                volume["volume_num"],
                volume_UUID,
                online_volume_disks,
                total_disks,
                VOLUME_STATE[min(2, bad_disks)],
            )
        )

        #Disk info
        disk_list += "<div class='volume'>"
        alignment = True
        for disk_UUID, disk in volume["disks"].items():
            #insert the disk info in here
            disk_list += create_html_volume_disk(
                ALIGNMENTS[alignment],
                "UUID: %s<br>Level:%s, Disknum: %s" % (
                    disk_UUID,
                    disk["level"],
                    disk["disk_num"],
                ),
                IMAGES[disk["state"]],
                HTML_OBJECTS[disk["state"]](disk, volume_UUID),
            )
            alignment = not alignment

        disk_list += "</div>"


    #sort out the disks:
    online_disks, offline_disks = util.sort_disks(available_disks)

    #Next handle the online disks
    disk_list += "<h2>All Online Disks</h2>"
    disk_list += (
        "<form action='/init' enctype='multipart/form-data'"
        + "id='init_form' method='GET'>"
    )
    #create a checkbox for each disk, that returns the disks UUID
    index = 0
    for disk_UUID, disk in online_disks.items():
        disk_list += "<div class='online-disk-option'>%s%s</div>" % (
            create_disk_info(disk),
            create_checkbox(index, disk_UUID, disk),
        )
        index += 1

    if len(online_disks) > 1:
        #add scratch mode and help box
        disk_list += (
            '<br><input type="checkbox" name="scratch" value="True" unchecked>'
            + '&nbsp&nbspFrom scratch&nbsp&nbsp'
            + '<div class="tooltip"><img src="/help_box.jpg" class="help-box">'
            + '<span class="tooltiptext">'
            + 'To restart the system, and override existing settings'
            + '</span></div>'
        )
        #submit form for init
        disk_list += (
            "<br><button type='submit' form='init_form' value='Submit'>"
            + "Create Volume</button></form>"
        )

    #Finally handle the offline disks
    disk_list += "<h2>All Offine Disks</h2>"
    disk_list += "<div class='disk-group'>"
    for disk_UUID, disk in offline_disks.items():
        disk_list += "<button class='offline-disk-option'>%s</button>" % (
            create_disk_info(disk)
        )
    disk_list += "</div>"

    return disk_list


def create_html_volume_disk(alignment_class, info, picture, html_obj):
    #we want to print the disk in the following way:
    # Disk info
    # picture
    # html_obj
    return (
        (
            "<div class='%s'>"
            + "<p>%s<p>"
            + "<img src='/%s' class='disk-img'><br>"
            + "%s"
            + "</div>"
        ) % (
            alignment_class,
            info,
            picture,
            html_obj
        )
    )


def create_checkbox(index, disk_UUID, disk):
    return (
        (
            '<input type="checkbox" name="disk%s" value="%s">'
        ) % (
            index,
            disk_UUID,
        )
    )

def create_disk_info(disk):
    return (
        (
            "<table>"
            + "<tr><td>UUID: %s</td>"
            + "<td>Last Notification: %.1f Seconds ago</td></tr>"
            + "<tr><td>UDP Address: %s</td>"
            + "<td>TCP Address: %s</td></tr>"
            + "</table>"
        ) % (
            disk["disk_UUID"],
            time.time() - disk["timestamp"],
            printable_address(disk["UDP_address"]),
            printable_address(disk["TCP_address"])
        )
    )

def create_volume_disk_info(disk, disk_num):
    return (
        (
            "<table>"
            + "<tr><td>UUID: %s</td>"
            + "<td>Disknum: %s</td></tr>"
            + "<tr><td>Level: %s</td>"
            + "<td>TCP Address: %s</td></tr>"
            + "</table>"
        ) % (
            disk["disk_UUID"],
            disk_num,
            disk["level"],
            printable_address(disk["address"])
        )
    )


def printable_address(address):
    return "%s%s%s" % (
        address[0],
        constants.ADDRESS_SEPERATOR,
        address[1],
    )
