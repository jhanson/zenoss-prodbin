#################################################################
#
#   Copyright (c) 2002 Zentinel Systems, Inc. All rights reserved.
#
#################################################################

__doc__="""Software

Software represents a software vendor's product.

$Id: Software.py,v 1.5 2003/03/08 18:34:24 edahl Exp $"""

__version__ = "$Revision: 1.5 $"[11:-2]

from Globals import DTMLFile
from Globals import InitializeClass
from AccessControl import ClassSecurityInfo

from AccessControl import Permissions as permissions

from Products.ZenRelations.RelSchema import *

from MEProduct import MEProduct
from ZenDate import ZenDate

def manage_addSoftware(context, id, title = None, REQUEST = None):
    """make a Software"""
    d = Software(id, title)
    context._setObject(id, d)
    if REQUEST is not None:
        REQUEST['RESPONSE'].redirect(context.absolute_url()+'/manage_main') 
                                     

addSoftware = DTMLFile('dtml/addSoftware',globals())


class Software(MEProduct):
    """Software object"""
    portal_type = meta_type = 'Software'

    _properties = (
        {'id':'installDate', 'type':'date', 'mode':''},
    )

    _relations = MEProduct._relations + (
        ("device", ToOne(ToManyCont, "Device", "software")),
    )

    factory_type_information = ( 
        { 
            'id'             : 'Software',
            'meta_type'      : 'Software',
            'description'    : """Class to manage product information""",
            'icon'           : 'Software_icon.gif',
            'product'        : 'ZenModel',
            'factory'        : 'manage_addSoftware',
            'immediate_view' : 'viewProductOverview',
            'actions'        :
            ( 
                { 'id'            : 'overview'
                , 'name'          : 'Overview'
                , 'action'        : 'viewSoftwareOverview'
                , 'permissions'   : (
                  permissions.view, )
                },
                { 'id'            : 'viewHistory'
                , 'name'          : 'Changes'
                , 'action'        : 'viewHistory'
                , 'permissions'   : (
                  permissions.view, )
                },
            )
          },
        )

    security = ClassSecurityInfo()

    def __init__(self, id, title=""):
        MEProduct.__init__(self, id, title)
        self._installDate = ZenDate("1968/1/8")

    
    def __getattr__(self, name):
        if name == 'installDate':
            return self._installDate.getDate()
        else:
            raise AttributeError, name

    
    def _setPropValue(self, id, value):
        """override from PerpertyManager to handle checks and ip creation"""
        self._wrapperCheck(value)
        if id == 'installDate':
            self.setInstallDate(value)
        else:    
            MEProduct._setPropValue(self, id, value)


    security.declareProtected('Change Device', 'setProduct')
    def setProduct(self, productName,  manufacturer="Unknown", 
                    newProductName="", REQUEST=None, **kwargs):
        """Set the product class of this software.
        """
        if not manufacturer: manufacturer = "Unknown"
        if newProductName: productName = newProductName
        prodobj = self.getDmdRoot("Manufacturers").createSoftwareProduct(
                                    productName, manufacturer, **kwargs)
        prodobj.instances.addRelation(self)
        if REQUEST:
            REQUEST['message'] = ("Set Manufacturer %s and Product %s at time:" 
                                    % (manufacturer, productName))
            return self.callZenScreen(REQUEST)


    def setProductKey(self, prodKey):
        """Set the product class of this software by its productKey.
        """
        prodobj=self.getDmdRoot("Manufacturers").createSoftwareProduct(prodKey)
        prodobj.instances.addRelation(self)


    def getProductKey(self):
        """Get the product class of this software.
        """
        pclass = self.productClass()
        if pclass: return pclass.productKey
        return ""


    def name(self):
        """Return the name of this software (from its softwareClass)
        """
        pclass = self.productClass()
        if pclass: return pclass.name
        return ""


    def version(self):
        """Return the verion of this software (from its softwareClass)
        """
        pclass = self.productClass()
        if pclass: return pclass.version
        return ""
       

    def build(self):
        """Return the build of this software (from its softwareClass)
        """
        pclass = self.productClass()
        if pclass: return pclass.build
        return ""
       

    def manufacturerName(self):
        """Return the manufacturer of this software (from its softwareClass)
        """
        pclass = self.productClass()
        if pclass: return pclass.getManufacturerName()
        return ""

    def getManufacturerLink(self):
        pclass = self.productClass()
        if pclass: return pclass.manufacturer.getPrimaryLink()
        return ""

    def getProductLink(self):
        return self.productClass.getPrimaryLink()


    def getInstallDate(self):
        return self._installDate.getDate()


    def setInstallDate(self, value):
        self._installDate.setDate(value) 


    def installDateString(self):
        return self._installDate.getString()


InitializeClass(Software)
