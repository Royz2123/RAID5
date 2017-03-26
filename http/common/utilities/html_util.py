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
    header=constants.HTML_ERROR_HEADER
):
    return (
        "<HTML><HEAD><TITLE>%s</TITLE></HEAD><BODY>%s</BODY></HTML>"
        % (
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
    disk_num = 0
    for disk in disks:
        table += (
            (
                '<tr align="center"> %s </tr>'
            ) % (
                '<td> %s </td>' % disk_num +
                "<td> %s </td>" % str(disk["address"]) +
                "<td> %s </td>" % disk["disk_UUID"] +
                "<td> %s </td>" % disk["level"] +
                '<td> %s,\t Toggle: %s </td>' % (
                    constants.DISK_STATES[disk["state"]],
                    toggle_state_form(
                        disk_num,
                        disk["state"]
                    )
                )
            )
        )
        disk_num += 1
    return table

def toggle_state_form(disk_num, disk_state):
    new_disk_state = not disk_state

    return (
        '<form action="/togglestate" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disknum" value=%s>'
        + '<input type="submit" value=%s>'
        + '</form>'
    ) % (
        disk_num,
        constants.DISK_STATES[new_disk_state]
    )
