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
    header=constants.HTML_ERROR_HEADER,
    refresh=None
):
    refresh_header = ""
    if refresh is not None:
        refresh_header = (
            "<meta http-equiv='refresh' content='%s'>"
            % (
                refresh
            )
        )
    return (
        (
            "<HTML><HEAD>%s<TITLE>%s</TITLE></HEAD>"
            + "<BODY>%s</BODY></HTML>"
        )% (
            refresh_header,
            header,
            content
        )
    )


def create_disks_table(disks):
    common_UUID = "undefined"
    if len(disks) != 0:
        common_UUID = disks[0]["common_UUID"]

    table = '<table border="5" width="50%" cellpadding="4" cellspacing="3">'
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
    disknum = 0
    for disk in disks:
        if disk["state"] == constants.ONLINE:
            table += (
                (
                    '<tr align="center"> %s </tr>'
                ) % (
                    '<td> %s </td>' % disknum +
                    "<td> %s </td>" % str(disk["address"]) +
                    "<td> %s </td>" % disk["disk_UUID"] +
                    "<td> %s </td>" % disk["level"] +
                    '<td> %s\t : %s </td>' % (
                        constants.DISK_STATES[disk["state"]],
                        disconnect_form(
                            disknum,
                        )
                    )
                )
            )
        else:
            table += (
                (
                    '<tr align="center"> %s </tr>'
                ) % (
                    '<td> %s </td>' % disknum
                    + '<td colspan="4"><br> %s </td>' % (
                        connect_form(disknum)
                    )
                )
            )
        disknum += 1
    return table

def disconnect_form(disk_num):
    return (
        '<form action="/disconnect" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disknum" value=%s>'
        + '<input type="submit" value="Disconnect">'
        + '</form>'
    ) % (
        disk_num,
    )

def connect_form(disk_num):
    return (
        '<form action="/connect" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disknum" value=%s>Address: '
        + '<input type="text" name="address">&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp'
        + '<input type="submit" value="Connect">'
        + '</form>'
    ) % (
        disk_num,
    )
