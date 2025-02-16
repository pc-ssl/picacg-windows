import base64
import json
import os
import random
import time

from PySide2 import QtWidgets, QtWebSockets
from PySide2.QtCore import Signal, QTimer, QSize, Qt
from PySide2.QtGui import QPixmap, QFont
from PySide2.QtWidgets import QFileDialog, QLabel, QListWidgetItem

from conf import config
from src.qt.chat.chat_ws import ChatWebSocket
from src.qt.chat.qtchatroommsg import QtChatRoomMsg
from src.qt.com.qtbubblelabel import QtBubbleLabel
from src.qt.com.qticon import IconList
from src.qt.com.qtloading import QtLoading
from src.qt.util.qttask import QtTask
from src.user.user import User
from src.util import Log
from src.util.status import Status
from ui.chatroom import Ui_ChatRoom


class QtChatRoom(QtWidgets.QWidget, Ui_ChatRoom):
    websocket = Signal(int, str)

    Enter = 1
    Leave = 2
    Msg = 3
    Error = 4
    SendImg = 5
    SendMsg2 = 6

    def __init__(self):
        super(self.__class__, self).__init__()
        Ui_ChatRoom.__init__(self)
        self.setupUi(self)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWindowTitle("聊天室")
        self.url = ""
        self.socket = ChatWebSocket(self)
        self.websocket.connect(self.HandlerInfo)
        self.timer = QTimer(self)
        self.resize(800, 1000)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.SendPing)
        self.scrollArea.verticalScrollBar().rangeChanged.connect(self.SliderScroll)
        self.maxScrollArea = self.scrollArea.verticalScrollBar().value()

        self.msgInfo = {}
        self.removeMsgId = 0
        self.indexMsgId = 0
        self.maxMsgInfo = 1000
        self.loadingForm = QtLoading(self)
        self.replyName = ""
        self.reply = ""
        self.atName = ""
        self.listWidget.setFrameShape(self.listWidget.NoFrame)  # 无边框
        self.listWidget.setFlow(self.listWidget.LeftToRight)  # 从左到右
        self.listWidget.setWrapping(True)
        self.listWidget.setResizeMode(self.listWidget.Adjust)
        self.listWidget.itemClicked.connect(self.IconSelect)
        self.cachePath = "."
        f = QFont()
        f.setPointSize(14)
        for icon in IconList:
            item = QListWidgetItem(icon)
            item.setTextAlignment(Qt.AlignCenter)
            item.setFont(f)
            item.setSizeHint(QSize(40, 40))
            self.listWidget.addItem(item)
        self.listWidget.setVisible(False)

    def closeEvent(self, event) -> None:
        self.socket.Stop()
        return super(self.__class__, self).closeEvent(event)

    def GetName(self):
        return self.__class__.__name__

    def Error(self, error):
        return

    def JoinRoom(self):
        Log.Info("join room, Url:{}".format(self.url))
        self.LoginRoom()
        self.timer.start()
        self.loadingForm.close()
        return

    def LoginRoom(self):
        data = ["init", User().userInfo]
        msg = "42{}".format(json.dumps(data))
        self.socket.Send(msg)

    def SendPing(self):
        msg = "2"
        self.socket.Send(msg)
        Log.Info("recv websocket info: ping")

    def RecvPong(self):
        return

    def LeaveRoom(self):
        Log.Info("level room, Url:{}".format(self.url))
        self.timer.stop()
        self.close()
        self.url = ""
        for info in self.msgInfo.values():
            info.setParent(None)
        self.msgInfo.clear()
        self.indexMsgId = 0
        self.removeMsgId = 0
        return

    def ReceviveMsg(self, msg):
        Log.Info("recv websocket info: " + msg)
        if msg == "3":
            self.RecvPong()
        elif msg[:2] == "42":
            data = json.loads(msg[2:])
            if len(data) < 2:
                return
            elif data[0] == "new_connection":
               self._UpdateOnline(data[1])
            elif data[0] == "broadcast_message":
               self._RecvBroadcastMsg(data[1])
            elif data[0] == "broadcast_ads":
                self._RecvAdsMsg(data[1])
            elif data[0] == "broadcast_image":  # receive_notification
                self._RecvBroadcastMsg(data[1])
            elif data[0] == "receive_notification":
                pass
            elif data[0] == "broadcast_audio":
                self._RecvBroadcastMsg(data[1])
            elif data[0] == "send_image":
                self._RecvBroadcastMsg(data[1])
            elif data[0] == "send_message":
                self._RecvBroadcastMsg(data[1])
            else:
                a = data[1]
        return

    def _UpdateOnline(self, data):
        num = data.get("connections")
        self.numLabel.setText("在线人数："+str(num))
        return

    def _RecvBroadcastMsg(self, data):
        msg = data.get("message", "")
        name = data.get("name", "")
        level = data.get("level")
        title = data.get("title")
        info = QtChatRoomMsg(self)
        at = data.get('at')
        if at:
            msg = "<font color=#1661ab>{}</font>".format(at.replace("嗶咔_", "@")) + "\n" + msg
        info.commentLabel.setText(msg)
        info.nameLabel.setText(name)
        info.levelLabel.setText(" LV"+str(level)+" ")
        info.titleLabel.setText(" " + title + " ")
        info.indexLabel.setText("{}楼".format(str(self.indexMsgId + 1)))
        # info.numLabel.setText("{}楼".format(str(self.indexMsgId+1)))
        info.infoLabel.setText(data.get("platform", "")+" ")
        imageData = data.get("image")
        if not imageData:
            replay = data.get("reply", "")
            replayName = data.get("reply_name", "")
            if replay and replayName:
                info.replayLabel.setText(replayName + "\n" + replay)
                info.replayLabel.setVisible(True)
            else:
                info.replayLabel.setVisible(False)
        else:
            info.replayLabel.setVisible(False)
            imageData = imageData.split(",", 1)
            if len(imageData) >= 2:
                byte = base64.b64decode(imageData[1])
                info.SetPictureComment(byte)

        audio = data.get("audio")
        if audio:
            info.replayLabel.setVisible(False)
            info.commentLabel.setVisible(False)
            info.toolButton.setVisible(True)
            try:
                saveName = str(int(time.time())) + "_" + str(random.randint(1, 1000)) + ".3gp"
                info.toolButton.setText(saveName)
                path = os.path.join(config.SavePath, config.ChatSavePath)
                saveName = os.path.join(path, saveName)
                info.audioData = saveName
                if not os.path.isdir(path):
                    os.makedirs(path)
                f = open(saveName, "wb")
                f.write(audio.encode("utf-8"))
                f.close()
            except Exception as es:
                Log.Error(es)
        else:
            info.toolButton.setVisible(False)

        url = data.get("avatar")
        if url and config.IsLoadingPicture:
            if isinstance(url, dict):
                QtTask().AddDownloadTask(url.get("fileServer"), url.get("path"), None, self.LoadingPictureComplete, True, self.indexMsgId, True, self.GetName())
            else:
                QtTask().AddDownloadTask(url, "", None, self.LoadingPictureComplete, True, self.indexMsgId, True,
                                         self.GetName())
        character = data.get("character", "")
        if "pica-web.wakamoment.tk" not in character and config.IsLoadingPicture:
            QtTask().AddDownloadTask(character, "", None, self.LoadingHeadComplete, True, self.indexMsgId, True,
                                     self.GetName())
        self.verticalLayout_2.addWidget(info)
        self.msgInfo[self.indexMsgId] = info
        self.indexMsgId += 1
        if len(self.msgInfo) > self.maxMsgInfo:
            removeInfo = self.msgInfo.get(self.removeMsgId)
            if removeInfo:
                removeInfo.setParent(None)
                self.msgInfo.pop(self.removeMsgId)
            self.removeMsgId += 1
        return

    def LoadingPictureComplete(self, data, status, index):
        if status == Status.Ok:
            widget = self.msgInfo.get(index)
            if not widget:
                return
            widget.SetPicture(data)

    def LoadingHeadComplete(self, data, status, index):
        if status == Status.Ok:
            widget = self.msgInfo.get(index)
            if not widget:
                return
            widget.SetHeadPicture(data)

    def _RecvAdsMsg(self, data):
        return

    def OpenChat(self, url, name):
        if self.url:
            return
        self.show()
        self.atLabel.setVisible(False)
        self.replyLabel.setVisible(False)
        self.url = url
        self.nameLabel.setText(name)
        self.loadingForm.show()
        self.socket.Start(self.url)
        return

    def HandlerInfo(self, taskType, data):
        if taskType == self.Leave:
            self.LeaveRoom()
        elif taskType == self.Msg:
            self.ReceviveMsg(data)
        elif taskType == self.Enter:
            self.JoinRoom()
        elif taskType == self.Error:
            pass
        elif taskType == self.SendImg:
            self.picButton.setEnabled(True)
            self.picButton.setText("图片")
            self.ReceviveMsg(data)
        elif taskType == self.SendMsg2:
            self.ReceviveMsg(data)

    def SliderScroll(self):
        # print(self.scrollArea.verticalScrollBar().value(), self.maxScrollArea,
        #       self.scrollArea.verticalScrollBar().maximum())
        if self.scrollArea.verticalScrollBar().value() == self.maxScrollArea:
            self.scrollArea.verticalScrollBar().setValue(self.scrollArea.verticalScrollBar().maximum())
        self.maxScrollArea = self.scrollArea.verticalScrollBar().maximum()

    def SendMsg(self, imageData=None):
        msg = self.textEdit.toPlainText()
        if not msg and not imageData:
            return
        info = dict(User().userInfo)
        if User().avatar:
            info['avatar'] = "https://storage.wikawika.xyz" + "/static/" + User().avatar.get("path")
        info['audio'] = ""
        info['block_user_id'] = ""
        info['platform'] = "windows"
        if not imageData:
            info['reply_name'] = ""
            info['at'] = ""
            info['reply'] = ""
            if self.atLabel.isVisible() and self.atName:
                info['at'] = "嗶咔_" + self.atName
            if self.replyLabel.isVisible() and self.replyName:
                info['reply'] = self.reply
                info['reply_name'] = self.replyName
            info['message'] = msg
            sendType = "send_message"
            data = "42" + json.dumps([sendType, info])
            self.textEdit.setText("")
            self.replyLabel.setVisible(False)
            self.atLabel.setVisible(False)
        else:
            info['image'] = imageData
            sendType = "send_image"
            data = "42" + json.dumps([sendType, info])
            self.picButton.setEnabled(False)
            self.picButton.setText("正在发送")

        self.socket.Send(data)

    def OpenPicture(self):
        try:
            data, name, picFormat = QtBubbleLabel.OpenPicture(self, self.cachePath)
            if data:
                self.cachePath = os.path.dirname(name)
                imgData = base64.b64encode(data).decode("utf-8")
                imgData = "data:image/" + picFormat + ";base64," + imgData
                self.SendMsg(imgData)
        except Exception as ex:
            Log.Error(ex)
        return

    def Test(self):
        pass

    def SetAtLabel(self, name):

        self.atName = name
        self.atLabel.setText("@" + name + ":")
        self.atLabel.setVisible(True)

    def SetReplyLabel(self, name, text):
        self.replyName = name
        self.reply = text
        self.replyLabel.setText(name + ":" + text)
        self.replyLabel.setVisible(True)

    def SetEnable1(self):
        self.atLabel.setVisible(False)
        return

    def SetEnable2(self):
        self.replyLabel.setVisible(False)
        return

    def OpenIcon(self):
        self.listWidget.setVisible(not self.listWidget.isVisible())
        return

    def IconSelect(self, item):
        data = item.text()
        text = self.textEdit.toPlainText()
        self.textEdit.setText(text + data)
        self.listWidget.setVisible(False)
