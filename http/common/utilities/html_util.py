# -*- coding: utf-8 -*-
import errno
import logging
import os
import select
import time
import traceback

from http.common.utilities import constants

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


def create_disks_table(disks):
    common_UUID = "undefined"
    if len(disks) != 0:
        common_UUID = disks[0]["common_UUID"]

    table = '<table border="5" cellpadding="4" cellspacing="3">'
    table += (
        '<tr><th colspan="5"><br><h3> Manage Disks<br>System UUID: %s '
        '</h3></th></tr>' % common_UUID
    )
    table += '<tr><th colspan="5"> Disks: %s </th></tr>' % len(disks)
    table += (
        (
            "<tr><th> %s </th><th> %s </th><th> %s"
            + "</th><th> %s </th><th> %s </th></tr>"
        ) % (
            "",
            "Disk Address",
            "Disk UUID",
            "Level",
            "State",
        )
    )
    disk_num = 0
    for disk in disks:
        if disk["state"] == constants.OFFLINE:
            table += (
                (
                    '<tr align="center"> %s </tr>'
                ) % (
                    '<td> %s </td>' % disk_num
                    + '<td colspan="4"><br> %s </td>' % (
                        connect_form(disk_num)
                    )
                )
            )
        else:
            table += (
                (
                    '<tr align="center"> %s </tr>'
                ) % (
                    '<td> %s </td>' % disk_num +
                    "<td> %s </td>" % printable_address(disk["address"]) +
                    "<td> %s </td>" % disk["disk_UUID"] +
                    "<td> %s </td>" % disk["level"] +
                    '<td> %s:<br>%s </td>' % (
                        constants.DISK_STATES[disk["state"]],
                        (
                            (
                                (disk["state"] == constants.ONLINE)
                                * disconnect_form(disk_num)
                            ) + (
                                (disk["state"] == constants.REBUILD)
                                * html_progress_bar(disks, disk_num)
                            )
                        )
                    )
                )
            )

        disk_num += 1
    return table


def create_disks_list(disks):
    online_disks, offline_disks = sort_disks(disks)

    #print online disks
    disk_list = "<h2>Online Disks</h2>"
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
            + "Submit</button></form>"
        )

    #show offline disks
    disk_list += "<h2>Offine Disks</h2>"
    disk_list += "<div class='disk-group'>"
    for index, disk in offline_disks.items():
        disk_list += "<button class='offline-disk-option'>%s</button>" % (
            create_disk_info(disk)
        )
    disk_list += "</div>"

    return disk_list


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
            disk["UUID"],
            time.time() - disk["timestamp"],
            printable_address(disk["UDP_address"]),
            printable_address(disk["TCP_address"])
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
