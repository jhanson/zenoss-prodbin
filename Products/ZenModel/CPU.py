#################################################################
#
#   Copyright (c) 2002 Zenoss, Inc. All rights reserved.
#
#################################################################

__doc__="""CPU

CPU is a collection of devices and subsystems that make
up a business function

$Id: CPU.py,v 1.7 2004/04/06 22:33:24 edahl Exp $"""

__version__ = "$Revision: 1.7 $"[11:-2]

from Globals import DTMLFile
from Globals import InitializeClass

from Products.ZenRelations.RelSchema import *

from HWComponent import HWComponent

class CPU(HWComponent):
    """CPU object"""

    portal_type = meta_type = 'CPU'

    socket = 0
    clockspeed = 0
    extspeed = 0
    voltage = 0
    cacheSizeL1 = 0
    cacheSizeL2 = 0

    _properties = (
         {'id':'socket', 'type':'int', 'mode':'w'},
         {'id':'clockspeed', 'type':'int', 'mode':'w'},     #MHz
         {'id':'extspeed', 'type':'int', 'mode':'w'},       #MHz
         {'id':'voltage', 'type':'int', 'mode':'w'},        #Millivolts
         {'id':'cacheSizeL1', 'type':'int', 'mode':'w'},    #KBytes
         {'id':'cacheSizeL2', 'type':'int', 'mode':'w'},    #KBytes
    )    
    
    _relations = HWComponent._relations + (
        ("hw", ToOne(ToManyCont, "DeviceHW", "cpus")),
        )

    
    factory_type_information = ( 
        { 
            'id'             : 'CPU',
            'meta_type'      : 'CPU',
            'description'    : """Arbitrary device grouping class""",
            'icon'           : 'CPU_icon.gif',
            'product'        : 'ZenModel',
            'factory'        : 'manage_addCPU',
            'immediate_view' : 'viewCPU',
            'actions'        :
            ( 
                { 'id'            : 'status'
                , 'name'          : 'Status'
                , 'action'        : 'viewCPU'
                , 'permissions'   : ('View',)
                },
                { 'id'            : 'viewHistory'
                , 'name'          : 'Changes'
                , 'action'        : 'viewHistory'
                , 'permissions'   : ('View',)
                },
            )
          },
        )

InitializeClass(CPU)
