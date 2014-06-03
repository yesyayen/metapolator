#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import ujson

from metapolator.metapost import Metapost
from metapolator.models import GlyphPointParam, GlyphPoint, Glyph, LocalParam

# todo: move mflist to another common module
from metapolator.xmltomf_pen import mflist

from sqlalchemy.orm import joinedload
from metapolator.base.dbapi import query

def get_glyph_info_from_log(log_filename, glyphid=None, master=None):
    """ Returns json with glyph data from generated by metapost log file. """
    try:
        fp = open(log_filename)
        content = fp.read()
        fp.close()
        result = get_json(content, glyphid=glyphid, master=master)
        return result
    except (IOError, OSError):
        pass
    return []

def get_glyph_points_from_db(master, glyphid):
    """ Returns json with information about glyphs' points including coords
        and point parameters.

        Example result:
        ```yaml
        ---
          width: 1680
          points:
           -
             x: 12
             y: 123
             pointnr: 1
             iszpoint: true
             data:
               width: 1680
               width_new: 1490
               # then list of another point parameters
        ```
    """
    # todo: move mflist to another common module
    glyph = Glyph.get(master_id=master.id, name=glyphid)
    
    localparam = LocalParam.get(id=master.idlocala)
    
    # this is still not fast, but it's 5 times faster than without
    # .options(joinedload(GlyphPoint.glyphpoint)) option,
    # FIXME: queries like this belong explicitly into model-land
    points = (GlyphPoint
        .filter(glyph_id=glyph.id)
        .join(GlyphPoint.glyphpoint)
        .options(joinedload(GlyphPoint.glyphpoint))
        .order_by(GlyphPoint.pointnr.asc())
    ).all()
    
    _points = []
    for point in points:
        param = point.glyphpoint[0] # FIXME: bad naming here, see comment in GlyphPointParam
        
        iszpoint = False
        if re.match('z(\d+)[lr]', param.pointname):
            iszpoint = True

        x = point.x
        if localparam:
            x += localparam.px

        params = param.as_dict()
        params.update({'width': glyph.width})
        params.update({'width_new': glyph.width_new})
        _points.append({'x': x, 'y': point.y, 'pointnr': point.pointnr,
                        'iszpoint': iszpoint, 'data': params})
    return {'width': glyph.width, 'points': _points}

def get_json(content, glyphid=None, master=None):
    """ Returns json with glyph data from raw content generated
        by metapost.

        Example result:
        ```yaml
        ---
        -
          contours:
            -
              -
                controls:
                  - # control in
                    x: 34
                    y: 15
                  - # control out
                    x: 0
                    y: 98
                x: 12
                y: 101
          height: 1080
          minx: 0
          miny: 0
          name: 65
          width: 1680
          zpoints: {} # described in `get_glyph_points_from_db`
        ```
    """
    contour_pattern = re.compile(r'Filled\scontour\s:\n(.*?)..cycle',
                                 re.I | re.S | re.M)
    point_pattern = re.compile(r'\(([-\d.]+),([-\d.]+)\)..controls\s'
                               r'\(([-\d.]+),([-\d.]+)\)\sand\s'
                               r'\(([-\d.]+),([-\d.]+)\)')

    pattern = re.findall(r'\[(\d+)\]\s+Edge structure(.*?)End edge', content,
                         re.I | re.DOTALL | re.M)
    
    glyphs = []
    for glyph, edge in pattern:
        # there are probably a lot of glyphs in the log file. if we look
        # at the wrong glyph we skip it.
        # note that: glyphid == mflist[int(glyph) - 1]
        if glyphid and glyphid != mflist[int(glyph) - 1]:
            continue

        x_min = 0
        y_min = 0
        x_max = 0
        y_max = 0

        contours = []

        zpoints_names = []
        if master:
            params = (query(GlyphPointParam.pointname)
                .join(Glyph)
                .join(GlyphPoint)
                .filter(Glyph.master_id == master.id)
                .filter(Glyph.name == mflist[int(glyph) - 1])
                .filter(GlyphPoint.glyph_id == Glyph.id)
                .filter(GlyphPointParam.glyphpoint_id == GlyphPoint.id)
                .filter(GlyphPointParam.pointname.op('regexp')('z[0-9]+[rl]'))
                .order_by(GlyphPoint.pointnr.asc())
                .all()
            )
            zpoints_names = [p[0] for p in params]

        number = 0
        for ix, contour in enumerate(contour_pattern.findall(edge.strip())):
            contour = re.sub('\n(\S)', '\\1', contour)
            _contours = []
            handleIn_X, handleIn_Y = None, None

            for point in contour.split('\n'):
                point = point.strip().strip('..')
                match = point_pattern.match(point)
                if not match:
                    continue

                X = match.group(1)
                Y = match.group(2)

                handleOut_X = match.group(3)
                handleOut_Y = match.group(4)

                controlpoints = [{'x': 0, 'y': 0},
                                 {'x': handleOut_X, 'y': handleOut_Y}]
                if handleIn_X is not None and handleIn_Y is not None:
                    controlpoints[0] = {'x': handleIn_X, 'y': handleIn_Y}

                pointdict = {'x': X, 'y': Y, 'controls': controlpoints}
                _contours.append(pointdict)

                handleIn_X = match.group(5)
                handleIn_Y = match.group(6)

                x_min = min(x_min, x_max, float(X),
                            float(handleOut_X), float(handleIn_X))
                y_min = min(y_min, y_max, float(Y),
                            float(handleOut_Y), float(handleIn_Y))
                x_max = max(x_max, x_min, float(X),
                            float(handleOut_X), float(handleIn_X))
                y_max = max(y_max, y_min, float(Y),
                            float(handleOut_Y), float(handleIn_Y))

            if zpoints_names:
                zpoints = []
                ll = zpoints_names[number + 1: len(_contours) + number]
                if len(zpoints_names) > number:
                    zpoints = [zpoints_names[number]] + ll

                number += len(_contours)

                for zix, point in enumerate(_contours):
                    try:
                        point['pointname'] = zpoints[zix]
                    except IndexError:
                        pass

            if handleIn_X and handleIn_Y:
                _contours[0]['controls'][0] = {'x': handleIn_X,
                                               'y': handleIn_Y}

            contours.append(_contours)
        zpoints = []
        if master:
            zpoints = get_glyph_points_from_db(master, mflist[int(glyph) - 1])
            g = Glyph.get(master_id=master.id, name=mflist[int(glyph) - 1])
            maxx, minx = GlyphPoint.minmax(GlyphPoint.x, glyph_id=g.id)[0]
            maxy, miny = GlyphPoint.minmax(GlyphPoint.y, glyph_id=g.id)[0]

            if maxx is not None and minx is not None \
                    and maxy is not None and miny is not None:
                x_min = min(x_min, minx, x_max, maxx)
                x_max = max(x_min, minx, x_max, maxx)
                y_min = min(y_max, maxy, y_min, miny)
                y_max = max(y_max, maxy, y_min, miny)

        if x_min < 0:
            width = abs(x_max) + abs(x_min)
        else:
            width = abs(x_max)

        if y_min < 0:
            height = abs(y_max) + abs(y_min)
        else:
            height = abs(y_max)

        json = {'name': mflist[int(glyph) - 1], 'contours': contours,
                'minx': x_min, 'miny': y_min, 'zpoints': zpoints,
                'width': width, 'height': height}

        if master:
            # this is supposed to save the contours the first time they
            # where created, the bad thing is, that we have to check if
            # this already happend everytime, so I'll move it out of this method
            glyph_obj = Glyph.get(master_id=master.id, name=mflist[int(glyph) - 1])
            if glyph_obj and not glyph_obj.original_glyph_contours:
                glyph_obj.original_glyph_contours = ujson.dumps(contours)

        glyphs.append(json)

    return glyphs

def get_glyphs_jsondata(glyphid, master):
    """ Returns dictionary with glyph's information for concrete master and
        interpolated glyph.

        Example result:

        ```yaml
        ---
          M: {} # same as `get_json`
          R: {} # same as `get_json`
          master_id: 1
        ```
    """
    project = master.project
    masters = project.get_ordered_masters()
    glyph = Glyph.get(master_id=master.id, name=glyphid)
    
    metapost = Metapost(project)
    metapost.execute_interpolated_single(glyph)
    
    instancelog = project.get_instancelog(masters[0].version)
    M_glyphjson = get_glyph_info_from_log(instancelog, glyphid)

    metapost.execute_single(master, glyph)
    
    instancelog = project.get_instancelog(master.version, 'a')
    glyphjson = get_glyph_info_from_log(instancelog, glyphid, master)
    
    return {'M': M_glyphjson, 'R': glyphjson, 'master_id': master.id}
