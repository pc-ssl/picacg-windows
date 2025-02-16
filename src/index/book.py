import os

from src.server import Server, ToolUtil, Status
from src.util import Singleton, Log
from src.server import req


# 一张图
class Picture(object):
    def __init__(self):
        self.originalName = ""      # 文件名
        self.path = ""              # 下载路径
        self.fileServer = ""        # 下载服务器


# 一章节
class BookEps(object):
    def __init__(self):
        self.title = ""    # 章节名
        self.order = 0     # 排序
        self.id = ""       # id
        self.pages = 1     # 总页数
        self.pics = []     # 图片


# 一本书
class Book(object):
    def __init__(self):
        self._id = ""             # 唯一标识
        self.title = ""           # 标题
        self.author = ""          # 作者
        self.description = ""     # 描述
        self.epsCount = 0         # 章节数
        self.finished = False     # 是否完本
        self.categories = []      # 分类
        self.tags = []            # tag
        self.eps = []             # 章节列表BookEps
        self.epsDict = {}

    @property
    def id(self):
        return self._id


# 书的管理器
class BookMgr(Singleton):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.books = {}      # id: book

    @property
    def server(self):
        return Server()

    # 加载一本书的详细信息
    def AddBookById(self, bookId, bakParam):
        self.server.Send(req.GetComicsBookReq(bookId), bakParam=bakParam)

    def AddBookByIdBack(self, backData):
        try:
            if backData.res.data.get("comic"):
                info = self.books.get(backData.res.data['comic']['_id'])
                if not info:
                    info = Book()
                ToolUtil.ParseFromData(info, backData.res.data['comic'])
                self.books[info.id] = info
                return Status.Ok
            else:
                if backData.res.message == "under review":
                    return Status.UnderReviewBook
                Log.Warn("未找到书籍, bookId:{}, {}".format(backData.req.bookId, backData.res.message))
                return Status.NotFoundBook
        except Exception as es:
            Log.Error(es)
            return Status.NetError

    def AddBookEpsInfo(self, bookId, bakParam):
        page = 1
        self.server.Send(req.GetComicsBookEpsReq(bookId, page), bakParam=bakParam)

    def AddBookEpsInfoBack(self, backData):
        # 此处在线程中加载后续章节 TODO 章节太多时会导致太慢
        try:
            r = backData.res
            bookId = backData.req.bookId
            info = self.books.get(bookId)
            info.epsCount = r.data['eps']["total"]
            page = r.data['eps']["page"]

            # 重新初始化
            pages = r.data['eps']["pages"]
            limit = r.data['eps']["limit"]
            # 优化，如果分页已经加载好了，只需要重新加载更新最后一页即可

            for i, data2 in enumerate(r.data['eps']['docs']):
                # index = (page -1) * limit + i
                epsId = data2.get('id')
                if epsId in info.epsDict:
                    epsInfo = info.epsDict[epsId]
                else:
                    epsInfo = BookEps()
                    info.epsDict[epsId] = epsInfo
                    # info.eps.append(epsInfo)
                ToolUtil.ParseFromData(epsInfo, data2)

            loadPage = int((len(info.epsDict)-1) / limit + 1)
            nextPage = page + 1
            # 如果已经有了，则从最后那一页加载起就可以了
            if loadPage > nextPage:
                nextPage = loadPage

            info.eps = list(info.epsDict.values())
            info.eps.sort(key=lambda a: a.order)

            if nextPage <= pages:
                self.server.Send(req.GetComicsBookEpsReq(bookId, nextPage), bakParam=backData.bakParam, isASync=False)
                return Status.WaitLoad
            return Status.Ok
        except Exception as es:
            Log.Error(es)
            return Status.Error

    def AddBookEpsPicInfo(self, bookId, index=1, bakParam=0):
        page = 1
        self.server.Send(req.GetComicsBookOrderReq(bookId, index, page), bakParam=bakParam)

    def AddBookEpsPicInfoBack(self, backData):
        # 此处在线程中加载后续分页 TODO 分页太多时会导致太慢
        try:
            r = backData.res
            bookId = backData.req.bookId
            epsId = backData.req.epsId

            bookInfo = self.books.get(bookId)

            epsInfo = bookInfo.eps[epsId-1]
            page = r.data['pages']["page"]
            pages = r.data['pages']["pages"]
            limit = r.data['pages']["limit"]

            # 重新初始化
            # if page == 1:
            #     del epsInfo.pics[:]

            for i, data in enumerate(r.data['pages']['docs']):
                index = (page -1) * limit + i
                if len(epsInfo.pics) > index:
                    picInfo = epsInfo.pics[index]
                else:
                    picInfo = Picture()
                    epsInfo.pics.append(picInfo)
                ToolUtil.ParseFromData(picInfo, data['media'])

            loadPage = int((len(epsInfo.pics) - 1) / limit + 1)
            nextPage = page + 1
            # 如果已经有了，则从最后那一页加载起就可以了
            if loadPage > nextPage:
                nextPage = loadPage

            if nextPage <= pages:
                self.server.Send(req.GetComicsBookOrderReq(bookId, epsId, nextPage), bakParam=backData.bakParam, isASync=False)
                return Status.WaitLoad
            return Status.Ok
        except Exception as es:
            Log.Error(es)
            return Status.Error

    def _DownloadBoos(self, bookId):
        bookInfo = self.books.get(bookId)
        if not bookInfo:
            return
        for index, eps in enumerate(bookInfo.eps):
            if eps.pics:
                continue
            page = 0
            pages = 1
            while page < pages:
                r = self.server.Send(req.GetComicsBookOrderReq(bookId, index+1, page+1))
                page = r.data['pages']["page"]
                pages = r.data['pages']["pages"]
                for data in r.data['pages']['docs']:
                    epsInfo = Picture()
                    ToolUtil.ParseFromData(epsInfo, data['media'])
                    eps.pics.append(epsInfo)
        pass

    def SavePicture(self, r, savePath):
        if not os.path.exists(os.path.dirname(savePath)):
            os.makedirs(os.path.dirname(savePath))
        open(savePath, "wb").write(r.data.content)
        pass

    def DownloadPicture(self, url, path, backParam=""):
        self.server.Download(req.DownloadBookReq(url, path), bakParams=backParam)
