# -*- coding: utf-8 -*-
import errno
import logging
import os
import select
import time
import traceback

from http.common.utilities import constants


def make_html_page(content):
    return (
        "<HTML><HEAD><TITLE>%s</TITLE></HEAD><BODY>%s</BODY></HTML>"
        % (
            constants.HTML_ERROR_HEADER,
            content
        )
    )


def create_disks_table(self, disks):
    table = '<table border="5" width="50%" cellpadding="4" cellspacing="3">'
    table += '<tr><th colspan="5"><br><h3> Manage Disks </h3></th></tr>'
    table += '<tr><th colspan="5"> Disks: %s </th></tr>' % len(disks)
    table += (
        (
            "<tr><th> %s </th><th> %s </th><th> %s"
            + "</th><th> %s </th><th> %s </th></tr>"
        ) % (
            "",
            "Disk Address",
            "UUID",
            "Level",
            "State",
        )
    )
    disk_num = 1
    for disk in disks:
        table += '<tr align="center"> %s </tr>' % (
            '<td rowspan="2"> %s </td>' % disk_num +
            "<td> %s </td>" % disk["address"] +
            "<td> %s </td>" % disk["UUID"] +
            "<td> %s </td>" % disk["level"] +
            '<td rowspan="2"> %s,\t Toggle: %s </td>' % (
                disk["state"],
                toggle_state_form(
                    disk_num,
                    disk["state"]
                )
            )
        )
        disk_num += 1
    return table

def toggle_state_form(disk_num, disk_state):
    new_disk_state = "online"
    if disk_state == "online":
        new_disk_state = "offline"

    return (
        '<form action="togglestate" enctype="multipart/form-data" method="GET">'
        + '<input type="hidden" name="disk_num" value=%s>'
        + '<input type="submit" value=%s>'
        + '</form>'
    ) % (
        disk_num,
        new_disk_state
    )
