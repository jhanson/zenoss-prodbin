##############################################################################
#
# Copyright (C) Zenoss, Inc. 2009, 2010, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
The config module provides the implementation of the IConfigurationProxy
interface used within Zenoss Core. This implementation provides basic
configuration retrieval services directly from a remote ZenHub service.
"""

import logging
import time

import zope.component
import zope.interface

from cryptography.fernet import Fernet
from metrology import Metrology
from twisted.internet import defer
from twisted.python.failure import Failure

from Products.ZenHub.PBDaemon import HubDown
from Products.ZenUtils.observable import ObservableMixin

from .interfaces import (
    ICollector,
    ICollectorPreferences,
    IConfigurationProxy,
    IDataService,
    IEventService,
    IFrameworkFactory,
    IScheduledTask,
)
from .tasks import TaskStates

log = logging.getLogger("zen.collector.config")


class ConfigurationProxy(object):
    """
    This implementation of IConfigurationProxy provides basic configuration
    retrieval from the remote ZenHub instance using the remote configuration
    service proxy as specified by the collector's configuration.
    """

    zope.interface.implements(IConfigurationProxy)

    _cipher_suite = None

    def getPropertyItems(self, prefs):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        self._collector = zope.component.queryUtility(ICollector)
        serviceProxy = self._collector.getRemoteConfigServiceProxy()

        # Load any configuration properties for this daemon
        log.debug("Fetching daemon configuration properties")
        d = serviceProxy.callRemote("getConfigProperties")
        d.addCallback(lambda result: dict(result))
        return d

    def getThresholdClasses(self, prefs):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        self._collector = zope.component.queryUtility(ICollector)
        serviceProxy = self._collector.getRemoteConfigServiceProxy()

        log.debug("Fetching threshold classes")
        d = serviceProxy.callRemote("getThresholdClasses")
        return d

    def getThresholds(self, prefs):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        self._collector = zope.component.queryUtility(ICollector)
        serviceProxy = self._collector.getRemoteConfigServiceProxy()

        log.debug("Fetching collector thresholds")
        d = serviceProxy.callRemote("getCollectorThresholds")
        return d

    def getConfigProxies(self, prefs, ids=[]):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        self._collector = zope.component.queryUtility(ICollector)
        serviceProxy = self._collector.getRemoteConfigServiceProxy()

        log.debug("Fetching configurations")
        # get options from prefs.options and send to remote
        d = serviceProxy.callRemote(
            "getDeviceConfigs", ids, options=prefs.options.__dict__
        )
        return d

    def deleteConfigProxy(self, prefs, id):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        # not implemented in the basic ConfigurationProxy
        return defer.succeed(None)

    def updateConfigProxy(self, prefs, config):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        # not implemented in the basic ConfigurationProxy
        return defer.succeed(None)

    def getConfigNames(self, result, prefs):
        if not ICollectorPreferences.providedBy(prefs):
            raise TypeError("config must provide ICollectorPreferences")

        self._collector = zope.component.queryUtility(ICollector)
        serviceProxy = self._collector.getRemoteConfigServiceProxy()

        log.debug("Fetching device names")
        d = serviceProxy.callRemote(
            "getDeviceNames", options=prefs.options.__dict__
        )

        def printNames(names):
            log.debug(
                "workerid %s Fetched Names %s %s",
                prefs.options.workerid,
                len(names),
                names,
            )
            return names

        d.addCallback(printNames)
        return d

    @defer.inlineCallbacks
    def _get_cipher_suite(self):
        """
        Fetch the encryption key for this collector from zenhub.
        """
        if self._cipher_suite is None:
            self._collector = zope.component.queryUtility(ICollector)
            proxy = self._collector.getRemoteConfigServiceProxy()
            try:
                key = yield proxy.callRemote("getEncryptionKey")
                self._cipher_suite = Fernet(key)
            except Exception as e:
                log.warn("Remote exception: %s", e)
                self._cipher_suite = None
        defer.returnValue(self._cipher_suite)

    @defer.inlineCallbacks
    def encrypt(self, data):
        """
        Encrypt data using a key from zenhub.
        """
        cipher_suite = yield self._get_cipher_suite()
        encrypted_data = None
        if cipher_suite:
            try:
                encrypted_data = yield cipher_suite.encrypt(data)
            except Exception as e:
                log.warn("Exception encrypting data %s", e)
        defer.returnValue(encrypted_data)

    @defer.inlineCallbacks
    def decrypt(self, data):
        """
        Decrypt data using a key from zenhub.
        """
        cipher_suite = yield self._get_cipher_suite()
        decrypted_data = None
        if cipher_suite:
            try:
                decrypted_data = yield cipher_suite.decrypt(data)
            except Exception as e:
                log.warn("Exception decrypting data %s", e)
        defer.returnValue(decrypted_data)


class ConfigurationLoaderTask(ObservableMixin):
    """
    A task that periodically retrieves collector configuration via the
    IConfigurationProxy service.
    """

    zope.interface.implements(IScheduledTask)

    STATE_CONNECTING = "CONNECTING"
    STATE_FETCH_MISC_CONFIG = "FETCHING_MISC_CONFIG"
    STATE_FETCH_DEVICE_CONFIG = "FETCHING_DEVICE_CONFIG"
    STATE_PROCESS_DEVICE_CONFIG = "PROCESSING_DEVICE_CONFIG"

    _frameworkFactoryName = "core"

    def __init__(
        self,
        name,
        configId=None,
        scheduleIntervalSeconds=None,
        taskConfig=None,
    ):
        super(ConfigurationLoaderTask, self).__init__()
        self._fetchConfigTimer = Metrology.timer("collectordaemon.configs")

        # Needed for interface
        self.name = name
        self.configId = configId if configId else name
        self.state = TaskStates.STATE_IDLE

        self._dataService = zope.component.queryUtility(IDataService)
        self._eventService = zope.component.queryUtility(IEventService)

        if taskConfig is None:
            raise TypeError("taskConfig cannot be None")
        self._prefs = taskConfig
        self.interval = self._prefs.configCycleInterval * 60
        self.options = self._prefs.options

        self._daemon = zope.component.getUtility(ICollector)
        self._daemon.heartbeatTimeout = self.options.heartbeatTimeout
        log.debug(
            "Heartbeat timeout set to %ds", self._daemon.heartbeatTimeout
        )

        frameworkFactory = zope.component.queryUtility(
            IFrameworkFactory, self._frameworkFactoryName
        )
        self._configProxy = frameworkFactory.getConfigurationProxy()

        self.devices = []
        self.startDelay = 0

    def doTask(self):
        """
        Contact zenhub and gather configuration data.

        @return: A task to gather configs
        @rtype: Twisted deferred object
        """
        log.debug("%s gathering configuration", self.name)
        self.startTime = time.time()

        # Were we given a command-line option to collect a single device?
        if self.options.device:
            self.devices = [self.options.device]

        d = self._baseConfigs()
        self._deviceConfigs(d, self.devices)
        d.addCallback(self._notifyConfigLoaded)
        d.addErrback(self._handleError)
        return d

    def _baseConfigs(self):
        """
        Load the configuration that doesn't depend on loading devices.
        """
        d = self._fetchPropertyItems()
        d.addCallback(self._processPropertyItems)
        d.addCallback(self._fetchThresholdClasses)
        d.addCallback(self._processThresholdClasses)
        d.addCallback(self._fetchThresholds)
        d.addCallback(self._processThresholds)
        return d

    def _deviceConfigs(self, d, devices):
        """
        Load the device configuration
        """
        d.addCallback(self._fetchConfig, devices)
        d.addCallback(self._processConfig)

    def _notifyConfigLoaded(self, result):
        # This method is prematuraly called in enterprise bc
        # _splitConfiguration calls defer.succeed after creating
        # a new task for incremental loading
        self._daemon.runPostConfigTasks()
        return defer.succeed("Configuration loaded")

    def _handleError(self, result):
        if isinstance(result, Failure):
            log.error(
                "Task %s configure failed: %s",
                self.name,
                result.getErrorMessage(),
            )

            # stop if a single device was requested and nothing found
            if self.options.device or not self.options.cycle:
                self._daemon.stop()

            ex = result.value
            if isinstance(ex, HubDown):
                result = str(ex)
                # Allow the loader to be reaped and re-added
                self.state = TaskStates.STATE_COMPLETED
        return result

    def _fetchPropertyItems(self, previous_cb_result=None):
        return defer.maybeDeferred(
            self._configProxy.getPropertyItems, self._prefs
        )

    def _fetchThresholdClasses(self, previous_cb_result):
        return defer.maybeDeferred(
            self._configProxy.getThresholdClasses, self._prefs
        )

    def _fetchThresholds(self, previous_cb_result):
        return defer.maybeDeferred(
            self._configProxy.getThresholds, self._prefs
        )

    def _fetchConfig(self, result, devices):
        self.state = self.STATE_FETCH_DEVICE_CONFIG
        start = time.time()

        def recordTime(result):
            # get in milliseconds
            duration = int((time.time() - start) * 1000)
            self._fetchConfigTimer.update(duration)
            return result

        d = defer.maybeDeferred(
            self._configProxy.getConfigProxies, self._prefs, devices
        )
        d.addCallback(recordTime)
        return d

    def _processPropertyItems(self, propertyItems):
        log.debug("Processing received property items")
        self.state = self.STATE_FETCH_MISC_CONFIG
        if propertyItems:
            self._daemon._setCollectorPreferences(propertyItems)

    def _processThresholdClasses(self, thresholdClasses):
        log.debug("Processing received threshold classes")
        if thresholdClasses:
            self._daemon._loadThresholdClasses(thresholdClasses)

    def _processThresholds(self, thresholds):
        log.debug("Processing received thresholds")
        if thresholds:
            self._daemon._configureThresholds(thresholds)

    @defer.inlineCallbacks
    def _processConfig(self, configs, purgeOmitted=True):
        log.debug("Processing %s received device configs", len(configs))
        if self.options.device:
            configs = [
                cfg
                for cfg in configs
                if self.options.device in (cfg.id, cfg.configId)
            ]
            if not configs:
                log.error(
                    "Configuration for %s unavailable -- "
                    "is that the correct name?",
                    self.options.device,
                )

        if not configs:
            # No devices (eg new install), -d name doesn't exist or
            # device explicitly ignored by zenhub service.
            if not self.options.cycle:
                self._daemon.stop()
            defer.returnValue(["No device configuration to load"])

        self.state = self.STATE_PROCESS_DEVICE_CONFIG
        yield self._daemon._updateDeviceConfigs(configs, purgeOmitted)
        defer.returnValue(configs)

    def cleanup(self):
        pass  # Required by interface
