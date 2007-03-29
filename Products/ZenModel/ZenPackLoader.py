##############################################################################
#
#   Copyright (c) 2007 Zenoss, Inc.. 
#
###############################################################################

__doc__='Base Classes for loading gunk in a ZenPack'

import Globals
from Products.ZenReports.ReportLoader import ReportLoader
from Products.ZenUtils.Utils import getObjByPath

import os
import logging
log = logging.getLogger('zen.ZPLoader')

def findFiles(pack, directory, filter=None):
    result = []
    for p, ds, fs in os.walk(pack.path(directory)):
        if not os.path.split(p)[-1].startswith('.'):
            for f in fs:
                if filter is None or filter(f):
                    result.append(os.path.join(p, f))
    return result

def findDirectories(pack, directory):
    result = []
    for p, ds, fs in os.walk(pack.path(directory)):
        if not os.path.split(p)[-1].startswith('.'):
            for d in ds:
                result.append(os.path.join(p, d))
    return result

def branchAfter(filename, directory, prefix = ""):
    "return the branch after the given directory name"
    path = filename.split('/')
    return prefix + '/'.join(path[path.index(directory)+1:])


class ZenPackLoader:

    name = "Set This Name"

    def load(self, pack, app):
        """Load things from the ZenPack and put it 
        into the app"""

    def unload(self, pack, app):
        """Remove things from Zenoss defined in the ZenPack"""

    def list(self, pack, app):
        "List the items that would be loaded from the given (unpacked) ZenPack"

from xml.sax import saxutils, make_parser
from xml.sax.handler import ContentHandler

class ZPLObject(ZenPackLoader):

    name = "Objects"

    def load(self, pack, app):
        from Products.ZenRelations.ImportRM import ImportRM
        class AddToPack(ImportRM):
            def endElement(self, name):
                if name == 'object':
                    obj = self.objstack[-1]
                    log.debug('Now adding %s', obj.getPrimaryUrlPath())
                    try:
                        obj.buildRelations()
                        obj.removeRelation('pack')
                        obj.addRelation('pack', pack)
                    except Exception, ex:
                        log.exception("Error adding pack to %s",
                                      obj.getPrimaryUrlPath())
                    
                ImportRM.endElement(self, name)
        importer = AddToPack(noopts=True, app=app)
        importer.options.noindex = True
        for f in self.objectFiles(pack):
            log.info("Loading %s", f)
            importer.loadObjectFromXML(xmlfile=f)


    def parse(self, filename, handler):
        parser = make_parser()
        parser.setContentHandler(handler)
        parser.parse(open(filename))
        

    def unload(self, pack, app):
        from Products.ZenRelations.Exceptions import ObjectNotFound
        dmd = app.zport.dmd
        objs = pack.packables()
        objs.sort(lambda x, y: cmp(x.getPrimaryPath(), y.getPrimaryPath()))
        objs.reverse()
        for obj in objs:
            path = obj.getPrimaryPath()
            path, id = path[:-1], path[-1]
            obj = dmd.getObjByPath(path)
            if len(path) > 3:           # leave /Services, /Devices, etc.
                try:
                    try:
                        obj._delObject(id)
                    except ObjectNotFound:
                        obj._delOb(id)
                except (AttributeError, KeyError), ex:
                    log.warning("Unable to remove %s on %s", id,
                                '/'.join(path))

    def list(self, pack, app):
        return [obj.getPrimaryUrlPath() for obj in pack.packables()]
        

    def objectFiles(self, pack):
        def isXml(f): return f.endswith('.xml')
        return findFiles(pack, 'objects', isXml)


class ZPLReport(ZPLObject):

    name = "Reports"

    def load(self, pack, app):
        class HookReportLoader(ReportLoader):
            def loadFile(self, root, id, fullname):
                rpt = ReportLoader.loadFile(self, root, id, fullname)
                rpt.addRelation('pack', pack)
                return rpt
        rl = HookReportLoader(noopts=True, app=app)
        rl.options.force = True
        rl.loadDirectory(pack.path('reports'))

class ZPLDaemons(ZenPackLoader):

    name = "Daemons"

    def load(self, pack, app):
        for fs in findFiles(pack, 'daemons'):
            os.chmod(fs, 0755)

    def list(self, pack, app):
        return [branchAfter(d, 'daemons') for d in findFiles(pack, 'daemons')]


class ZPLModelers(ZenPackLoader):

    name = "Modeler Plugins"


    def list(self, pack, app):
        return [branchAfter(d, 'plugins')
                for d in findFiles(pack, 'modeler/plugins')]


class ZPLSkins(ZenPackLoader):

    name = "Skins"


    def load(self, pack, app):
        from Products.ZenUtils.Skins import registerSkin
        from Products.ZenUtils.Utils import getObjByPath
        registerSkin(app.zport.dmd, pack.path(''))


    def unload(self, pack, app):
        from Products.ZenUtils.Skins import unregisterSkin
        unregisterSkin(app.zport.dmd, pack.path(''))


    def list(self, pack, app):
        return [branchAfter(d, 'skins') for d in findDirectories(pack, 'skins')]
