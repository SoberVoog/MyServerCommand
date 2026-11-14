# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
import os
import time
from mod_log import logger as logger
ClientSystem = clientApi.GetClientSystemCls()

CHUNK_SIZE = 1024 * 1024
SERVER_NAMESPACE = "MSC"
SERVER_SYSTEM_NAME = "MscCommandServerSystem"


class MscCommandClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        super(MscCommandClientSystem, self).__init__(namespace, systemName)
        self.namespace = namespace
        self.systemName = systemName

        try:
            self.ListenForEvent(
                SERVER_NAMESPACE,
                SERVER_SYSTEM_NAME,
                "UploadFileRequestEvent",
                self,
                self.OnUploadFileRequest
            )
        except Exception:
            pass

        try:
            self.ListenForEvent(
                SERVER_NAMESPACE,
                SERVER_SYSTEM_NAME,
                "UploadFileFinishEvent",
                self,
                self.OnUploadFileFinish
            )
        except Exception:
            pass

    def OnUploadFileRequest(self, args):
        filePath = args.get('filePath', '')
        requestId = args.get('requestId', '')
        playerId = args.get('playerId', '')
        targetPath = args.get('targetPath', '')

        if not os.path.exists(filePath):
            return

        if not os.path.isfile(filePath):
            return

        fileSize = os.path.getsize(filePath)
        if fileSize == 0:
            return

        ext = os.path.splitext(filePath)[1].lower()
        if ext not in {'.zip', '.mcworld'}:
            return

        self._upload_file_async(filePath, requestId, playerId, targetPath)

    def _upload_file_async(self, filePath, requestId, playerId, targetPath):
        try:
            fileSize = os.path.getsize(filePath)
            totalChunks = (fileSize + CHUNK_SIZE - 1) // CHUNK_SIZE
            fileName = os.path.basename(filePath)

            with open(filePath, 'rb') as f:
                for chunkIndex in range(totalChunks):
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    self.NotifyToServer("UploadFileChunkEvent", {
                        "requestId": requestId,
                        "chunkIndex": chunkIndex,
                        "totalChunks": totalChunks,
                        "chunkData": chunk,
                        "fileName": fileName,
                        "playerId": playerId,
                        "targetPath": targetPath
                    })

        except Exception:
            pass

    def OnUploadFileFinish(self, args):
        success = args.get('success',False)
        message = args.get('message','')

    def Update(self):
        pass