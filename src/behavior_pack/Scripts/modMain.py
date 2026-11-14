# -*- coding: utf-8 -*-
from mod.common.mod import Mod
import mod.server.extraServerApi as serverApi
import mod.client.extraClientApi as clientApi
from mod_log import logger as logger
from Scripts.ServerSystem import MscCommandServerSystem
from Scripts.ClientSystem import MscCommandClientSystem

MOD_NAMESPACE = "MSC"
SERVER_SYSTEM_NAME = "MscCommandServerSystem"
CLIENT_SYSTEM_NAME = "MscCommandClientSystem"

@Mod.Binding(name="Scripts",version="1.0.0")
class Scripts(object):
    def __init__(self):
        self.serverSystem = None
        self.clientSystem = None
    @Mod.InitServer()
    def MscCommandServerInit(self):
        try:
            cls_path = "%s.%s" % (MscCommandServerSystem.__module__,MscCommandServerSystem.__name__)
            self.serverSystem = serverApi.RegisterSystem(
                MOD_NAMESPACE,
                SERVER_SYSTEM_NAME,
                cls_path
            )
        except Exception as e:
            logger.error("[MSC] Server init error: %s" % str(e))
            import traceback
            logger.error(traceback.format_exc())
            raise

    @Mod.InitClient()
    def MscCommandClientInit(self):
        logger.info("[MSC] ===== Client Init START =====")
        try:
            cls_path = "%s.%s" % (MscCommandClientSystem.__module__, MscCommandClientSystem.__name__)
            self.clientSystem = clientApi.RegisterSystem(
                MOD_NAMESPACE,
                CLIENT_SYSTEM_NAME,
                cls_path
            )
        except Exception as e:
            logger.error("[MSC] Client init error: %s" % str(e))
            import traceback
            logger.error(traceback.format_exc())
            raise

    @Mod.DestroyServer()
    def MscCommandServerDestroy(self):
        logger.info("[MSC] Server destroy")

    @Mod.DestroyClient()
    def MscCommandClientDestroy(self):
        logger.info("[MSC] Client destroy")
