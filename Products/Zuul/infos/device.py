###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2010, Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 as published by
# the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################

from itertools import imap
from zope.component import adapts
from zope.interface import implements
from Products.ZenModel.DeviceOrganizer import DeviceOrganizer
from Products.ZenUtils import IpUtil
from Products.Zuul.tree import TreeNode
from Products.Zuul.interfaces import IDeviceOrganizerNode
from Products.Zuul.interfaces import IDeviceOrganizerInfo
from Products.Zuul.interfaces import IDeviceInfo, IDevice, ICatalogTool
from Products.Zuul.infos import InfoBase
from Products.Zuul import getFacade, info
from Products.Zuul.marshalling import TreeNodeMarshaller

ORGTYPES = {
    'Devices':'DeviceClass',
    'Systems':'Systems',
    'Locations':'Location',
    'Groups':'DeviceGroups'
}

def _organizerWhere(uid):
    """
    Duplicating a little code in EventManagerBase so as to avoid pulling
    all the objects. When we fix the event system we can probably do away
    with this.
    """
    orgname = uid.lstrip('/zport/dmd')
    if orgname.startswith('Devices'):
        return "DeviceClass like '%s%%'" % orgname.lstrip('Devices')
    elif orgname.startswith('Groups'):
        return "DeviceGroups like '%%|%s%%'" % orgname.lstrip('Groups')
    elif orgname.startswith('Systems'):
        return "Systems like '%%|%s%%'" % orgname.lstrip('Systems')
    elif orgname.startswith('Locations'):
        return "Location like '%s%%'" % orgname.lstrip('Locations')


class DeviceOrganizerNode(TreeNode):
    implements(IDeviceOrganizerNode)
    adapts(DeviceOrganizer)

    @property
    def _evsummary(self):
        where = _organizerWhere(self.uid)
        return getFacade('device').getEventSummary(where=where)

    @property
    def children(self):
        cat = ICatalogTool(self._object)
        orgs = cat.search(DeviceOrganizer, paths=(self.uid,), depth=1)
        return imap(DeviceOrganizerNode, orgs)

    @property
    def text(self):
        # need to query the catalog from the permissions perspective of
        # the uid
        cat = ICatalogTool(self._object.unrestrictedTraverse(self.uid))
        numInstances = cat.count('Products.ZenModel.Device.Device', self.uid)
        text = super(DeviceOrganizerNode, self).text
        return {
            'text': text,
            'count': numInstances,
            'description': 'devices'
        }

    # All nodes are potentially branches, just some have no children
    leaf = False


class DeviceOrganizerTreeNodeMarshaller(TreeNodeMarshaller):
    """
    Doesn't get iconCls for each individually. Loads up max sevs for all nodes
    first, then each node can look up its severity from that single query.
    """
    def getSeverities(self):
        f = getFacade('event')
        root = self.root.uid.split('/')[3]
        orgcol = ORGTYPES[root]
        q = 'select %s, max(severity) from status group by %s' % (orgcol,
                                                                  orgcol)
        result = {}
        for org, sev in f._run_query(q, ()):
            for org in org.split('|'):
                result[org] = max(result.get(org, sev), sev)
        return sorted(result.items())

    def getKeys(self):
        keys = super(DeviceOrganizerTreeNodeMarshaller, self).getKeys()
        if 'iconCls' in keys:
            keys.remove('iconCls')
        return keys

    def marshal(self, keys=None, severities=None):
        obj = self.getValues(keys)
        if self.root.leaf:
            obj['leaf'] = True
        if severities is None:
            severities = self.getSeverities()

        name = '/' + self.root.uid.split('/', 4)[-1]

        zem = getFacade('event')._event_manager()
        sevnames = [c[0].lower() for c in reversed(zem.severityConversions)]
        sev = 0
        for p, s in severities:
            if p.startswith(name):
                sev = max(sev, s)
                if p==name:
                    break
        sev = sevnames[sev]
        obj['iconCls'] = 'tree-severity-icon-small-%s' % sev
        obj['children'] = []
        for childNode in self.root.children:
            # We want to adapt explicitly because the signature of marshal() is
            # different (we need to pass the severities dict down)
            node = DeviceOrganizerTreeNodeMarshaller(childNode)
            obj['children'].append(node.marshal(keys, severities))
        return obj


class DeviceInfo(InfoBase):
    implements(IDeviceInfo)
    adapts(IDevice)

    @property
    def device(self):
        return self._object.id

    def getDevice(self):
        return self.device

    def getIpAddress(self):
        if self._object.manageIp:
            return IpUtil.ipToDecimal(self._object.manageIp)

    def setIpAddress(self, ip=None):
        self._object.setManageIp(ip)

    ipAddress = property(getIpAddress, setIpAddress)

    def getProductionState(self):
        return self._object.convertProdState(self._object.productionState)

    def setProductionState(self, prodState):
        return getFacade('device').setProductionState(self.uid, prodState)

    productionState = property(getProductionState, setProductionState)

    def getPriority(self):
        return self._object.convertPriority(self._object.priority)

    def setPriority(self, priority):
        self._object.setPriority(priority)

    priority = property(getPriority, setPriority)

    def getCollectorName(self):
        return self._object.getPerformanceServerName()

    def setCollector(self, collector):
        self._object.setPerformanceMonitor(collector)

    collector = property(getCollectorName, setCollector)

    @property
    def events(self):
        manager = self._object.getEventManager()
        severities = (c[0].lower() for c in manager.severityConversions)
        counts = (s[2] for s in self._object.getEventSummary())
        return dict(zip(severities, counts))

    def availability(self):
        return self._object.availability().availability

    @property
    def status(self):
        return self._object.getPingStatus()<1

    @property
    def deviceClass(self):
        return info(self._object.deviceClass())

    @property
    def groups(self):
        return info(self._object.groups())

    @property
    def systems(self):
        return info(self._object.systems())

    @property
    def location(self):
        return info(self._object.location())

    @property
    def uptime(self):
        return self._object.uptimeStr()

    @property
    def firstSeen(self):
        return self._object.getCreatedTimeString()

    @property
    def lastChanged(self):
        return self._object.getLastChangeString()

    @property
    def lastCollected(self):
        return self._object.getSnmpLastCollectionString()

    def getComments(self):
        return self._object.comments

    def setComments(self, value):
        self._object.comments = value

    comments = property(getComments, setComments)

    @property
    def links(self):
        return self._object.getExpandedLinks()

    @property
    def locking(self):
        return {
            'updates': self._object.isLockedFromUpdates(),
            'deletion': self._object.isLockedFromDeletion(),
            'events': self._object.sendEventWhenBlocked()
        }

    def getTagNumber(self):
        return self._object.hw.tag

    def setTagNumber(self, value):
        self._object.hw.tag = value

    tagNumber = property(getTagNumber, setTagNumber)

    def getSerialNumber(self):
        return self._object.hw.serialNumber

    def setSerialNumber(self, value):
        self._object.hw.serialNumber = value

    serialNumber = property(getSerialNumber, setSerialNumber)

    @property
    def hwManufacturer(self):
        if self.hwModel is not None:
            return info(self.hwModel._object.manufacturer())

    @property
    def hwModel(self):
        if self._object.hw:
            return info(self._object.hw.productClass())

    @property
    def osManufacturer(self):
        if self.osModel is not None:
            return info(self.osModel._object.manufacturer())

    @property
    def osModel(self):
        if self._object.os:
            return info(self._object.os.productClass())

    @property
    def memory(self):
        return {
            'ram': self._object.hw.totalMemoryString(),
            'swap': self._object.os.totalSwapString()
        }

    def getRackSlot(self):
        return self._object.rackSlot

    def setRackSlot(self, value):
        self._object.rackSlot = value

    rackSlot = property(getRackSlot, setRackSlot)

    def getSnmpSysName(self):
        return self._object.snmpSysName

    def setSnmpSysName(self, value):
        self._object.snmpSysName = value

    snmpSysName = property(getSnmpSysName, setSnmpSysName)

    def getSnmpContact(self):
        return self._object.snmpContact

    def setSnmpContact(self, value):
        self._object.snmpContact = value

    snmpContact = property(getSnmpContact, setSnmpContact)

    def getSnmpLocation(self):
        return self._object.snmpLocation

    def setSnmpLocation(self, value):
        self._object.snmpLocation = value

    snmpLocation = property(getSnmpLocation, setSnmpLocation)

    def getSnmpAgent(self):
        return self._object.snmpAgent

    def setSnmpAgent(self, value):
        self._object.snmpAgent = value

    snmpAgent = property(getSnmpAgent, setSnmpAgent)

    @property
    def icon(self):
        return self._object.zIcon



class DeviceOrganizerInfo(InfoBase):
    implements(IDeviceOrganizerInfo)
    adapts(DeviceOrganizer)

    @property
    def path(self):
        return self._object.getPrimaryDmdId()

    @property
    def events(self):
        mgr = self._object.getEventManager()
        sevs = (c[0].lower() for c in mgr.severityConversions)
        counts = (s[2] for s in self._object.getEventSummary())
        return dict(zip(sevs, counts))


def _removeZportDmd(path):
    if path.startswith('/zport/dmd'):
        path = path[10:]
    return path

