# -*- coding: utf-8 -*-
import errno
import logging
import os
import select
import time
import traceback

from http.common.utilities import constants

ALIGNMENTS = {
    True : "left-volume-disk-pic",
    False : "right-volume-disk-pic",
}
IMAGES = {
    constants.OFFLINE : "offline_disk1.png",
    constants.ONLINE : "online_disk.png",
    constants.REBUILD : "rebuild_disk.gif"
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


def create_disks_list(available_disks, volume):
    online_disks, offline_disks = sort_disks(available_disks)

    disk_list = ""
    if len(volume) != 0:
        disk_list += "<h2>Volume</h2>"
        disk_list += "<div class='volume'>"

        alignment = True
        for disk_num in range(len(volume)):
            disk = volume[disk_num]

            #set the disk_list
            if disk["state"] == constants.OFFLINE:
                html_obj = connect_form(disk_num)
            elif disk["state"] == constants.REBUILD:
                html_obj = html_progress_bar(volume, disk_num)
            else:
                html_obj = disconnect_form(disk_num)

            disk_list += create_html_volume_disk(
                ALIGNMENTS[alignment],
                "UUID: %s<br>Level:%s, Disknum: %s" % (
                    disk["disk_UUID"],
                    disk["level"],
                    disk_num
                ),
                IMAGES[disk["state"]],
                html_obj,
            )
            alignment = not alignment
        disk_list += "</div>"

    #print online disks
    disk_list += "<h2>All Online Disks</h2>"
    disk_list += (
        "<form action='/init' enctype='multipart/form-data'"
        + "id='init_form' method='GET'>"
    )
    for index, disk in online_disks.items():
        disk_list += "<div class='online-disk-option'>%s%s</div>" % (
            create_disk_info(disk),
            create_checkbox(index, disk),
        )

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

    #show offline disks
    disk_list += "<h2>All Offine Disks</h2>"
    disk_list += "<div class='disk-group'>"
    for index, disk in offline_disks.items():
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



def create_checkbox(index, disk):
    return (
        (
            '<input type="checkbox" name="address%s" value="%s">'
        ) % (
            index,
            printable_address(disk["TCP_address"]),
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

#recieves a dict of disks and seperates into two: onlines and offlines
def sort_disks(disks):
    online_disks, offline_disks = {}, {}
    for index, disk in disks.items():
        if disk["state"] == constants.ONLINE:
            online_disks[index] = disk
        else:
            offline_disks[index] = disk
    return online_disks, offline_disks


def html_progress_bar(disks, disk_num):
    rebuild_prcntg = disks[disk_num]["cache"].get_rebuild_percentage()
    if rebuild_prcntg < 0:
        return "Rebuilding first from scratch..."
    return (
        "Rebuilding progress:<progress value='%s' max='100'></progress>"
        % (
            rebuild_prcntg
        )
    )

def disconnect_form(disk_num):
    return (
        '<form action="/disconnect" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disk_num" value=%s>'
        + '<input type="submit" value="Disconnect">'
        + '</form>'
    ) % (
        disk_num,
    )

def connect_form(disk_num):
    return (
        '<form action="/connect" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disk_num" value=%s>Address: '
        + '<input type="text" name="address">&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp'
        + '<input type="submit" value="Connect">'
        + '</form>'
    ) % (
        disk_num,
    )
