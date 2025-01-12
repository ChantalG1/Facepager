from PySide2.QtCore import *
from PySide2.QtWidgets import *
from database import *

class DataTree(QTreeView):

    nodeSelected = Signal(list)

    def __init__(self, parent=None):
        super(DataTree, self).__init__(parent)

        #self.setSortingEnabled(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QTreeView.SelectRows)
        self.setUniformRowHeights(True)


    def loadData(self, database):
        self.treemodel = TreeModel(database)
        self.setModel(self.treemodel)

    @Slot()
    def currentChanged(self, current, previous):
        super(DataTree, self).currentChanged(current, previous)
        self.nodeSelected.emit(current) #,self.selectionModel().selectedRows()

    @Slot()
    def selectionChanged(self, selected, deselected):
        super(DataTree, self).selectionChanged(selected, deselected)
        current = self.currentIndex()
        self.nodeSelected.emit(current)  # ,self.selectionModel().selectedRows()

    def selectedCount(self):
        indexes = self.selectionModel().selectedRows()
        return(len(indexes))

    def selectLastRow(self):
        QCoreApplication.processEvents()
        
        model = self.model()
        parent = QModelIndex()
        row = model.rowCount(parent)-1
         
        index = model.index(row, 0,parent)
        self.scrollTo(index)
        self.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.selectionModel().setCurrentIndex(index,QItemSelectionModel.Rows)
                
    def noneOrAllSelected(self):
        indexes = self.selectionModel().selectedRows()

        if len(indexes) == 0:
            return True
        else:
            model = self.model()
            indexes = [idx for idx in indexes if idx.parent() == self.rootIndex()]
            return len(indexes) == model.rootItem.childCount()


    def selectedIndexesAndChildren(self, persistent=False, filter={}, selectall = False): #, emptyonly = False

        #emptyonly=filter.get('childcount',None)
        level = filter.get('level', None)

        def getLevel(index):
            if not index.isValid():
                return -1

            treeitem = index.internalPointer()
            if treeitem.data is not None and treeitem.data['level'] is not None:
                return treeitem.data['level']
            else:
                return 0

        def checkFilter(index):
            if not index.isValid():
                return False

            treeitem = index.internalPointer()
            for key, value in filter.items():
                if treeitem.data is not None and treeitem.data[key] is not None:
                    orlist = value if type(value) is list else [value]
                    if not treeitem.data[key] in orlist:
                        return False

            return True

        def addIndex(index, selected = False):
            if self.selectionModel().isSelected(index):
                selected = True

            #if emptyonly:
            #    child=index.child(0,0)
            #    append = not child.isValid()

            if checkFilter(index) and selected:
                if persistent:
                    index_persistent = QPersistentModelIndex(index)
                    yield (index_persistent)
                else:
                    yield (index)

            if (level is None) or (level > getLevel(index)):
                self.model().fetchMore(index)

                row = 0
                while True:
                    if not index.isValid():
                        child = self.model().index(row, 0, index)
                    else:
                        child = index.child(row, 0)

                    if child.isValid():
                        yield from addIndex(child, selected)
                    else:
                        break

                    row += 1

        yield from addIndex(QModelIndex(), selectall)

class TreeItem(object):
    def __init__(self, model=None, parent=None, id=None, data=None):
        self.model = model

        self.id = id
        self.data = data

        self.parentItem = parent
        self.childItems = []

        self.loaded = False
        self._childcountallloaded = False
        self._childcountall = 0
        self._row = None

        if parent is not None:
            parent.appendChild(self)

    def appendChild(self, item, persistent=False):
        item.parentItem = self
        self.childItems.append(item)

        item._row = len(self.childItems)-1
        if persistent:
            self._childcountall += 1

    def removeChild(self, position):
        if position < 0 or position > len(self.childItems):
            return False
        child = self.childItems.pop(position)
        child.parentItem = None

        return True

    def child(self, row):
        return self.childItems[row]

    def parent(self):
        return self.parentItem

    def setParent(self, new_parent):
        self.parentItem.childItems.remove(self)
        self.parentItem = new_parent
        new_parent.childItems.append(self)

    def clear(self):
        self.childItems = []
        self.loaded = False
        self._childcountallloaded = False

    def remove(self, persistent=False):
        self.parentItem.removeChild(self, persistent)

    def removeChild(self, child, persistent=False):
        if child in self.childItems:
            rowidx = child.row()
            #del self.childItems[rowidx]
            self.childItems.remove(child)

            #Update row indexes
            for row in range(rowidx, len(self.childItems) - 1):
                self.childItems[row]._row = row

            if persistent:
                self._childcountall -= 1
                dbnode = self.dbnode()
                if dbnode:
                    dbnode.childcount -= 1

    def childCount(self):
        return len(self.childItems)

    def childCountAll(self):
        if not self._childcountallloaded:
            self._childcountall = Node.query.filter(Node.parent_id == self.id).count()
            self._childcountallloaded = True
        return self._childcountall

    #    def allIndexes(self):
    #        yield self
    #        for index in self.childItems:


    def parentid(self):
        return self.parentItem.id if self.parentItem else None

    def dbnode(self):
        if self.id:
            return Node.query.get(self.id)
        else:
            return None

    def level(self):
        if self.data is None:
            return 0
        else:
            return self.data['level']

    def row(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)

        return None


    def appendNodes(self, data, options, headers=None, delaycommit=False):
        dbnode = Node.query.get(self.id)
        if not dbnode:
            return False

        #filter response
        if options['nodedata'] is None:
            subkey = 0
            nodes = data
            offcut = None
        elif hasDictValue(data,options['nodedata']):
            subkey = options['nodedata'].rsplit('.', 1)[0]
            nodes = getDictValue(data, options['nodedata'], False)
            offcut = filterDictValue(data, options['nodedata'], False)
        else:
            subkey = options['nodedata'].rsplit('.', 1)[0]
            nodes = []
            offcut = data

        if not (type(nodes) is list):
            nodes = [nodes]
            fieldsuffix = ''
        else:
            fieldsuffix = '.*'

        newnodes = []

        def appendNode(objecttype, objectid, response, fieldsuffix = ''):
            new = Node(str(objectid), dbnode.id)
            new.objecttype = objecttype
            new.response = response if isinstance(response,Mapping) else {subkey : response}

            new.level = dbnode.level + 1
            new.querystatus = options.get("querystatus", "")
            new.querytime = str(options.get("querytime", ""))
            new.querytype = options.get('querytype', '')

            queryparams = {key : options.get(key,'') for key in  ['nodedata','basepath','resource']}
            queryparams['nodedata'] = queryparams['nodedata'] + fieldsuffix if queryparams['nodedata'] is not None else queryparams['nodedata']
            new.queryparams = queryparams

            newnodes.append(new)


        #empty records
        if len(nodes) == 0:
            appendNode('empty', '', {})

        #extracted nodes
        for n in nodes:
            appendNode('data', getDictValue(n, options.get('objectid', "")), n, fieldsuffix)

        #Offcut
        if offcut is not None:
            appendNode('offcut', dbnode.objectid, offcut)

        #Headers
        if options.get('saveheaders',False) and headers is not None:
            appendNode('headers',dbnode.objectid,headers)


        self.model.database.session.add_all(newnodes)
        self._childcountall += len(newnodes)
        dbnode.childcount += len(newnodes)

        self.model.newnodes += len(newnodes)
        self.model.nodecounter += len(newnodes)
        self.model.commitNewNodes(delaycommit)
        # self.model.database.session.commit()
        # self.model.layoutChanged.emit()


    def unpackList(self, key):
        dbnode = Node.query.get(self.id)

        nodes = getDictValue(dbnode.response, key, False)
        if not (type(nodes) is list):
            return False

        # extract nodes
        subkey = key.rsplit('.', 1)[0]
        newnodes = []
        for n in nodes:
            new = Node(dbnode.objectid, dbnode.id)
            new.objecttype = 'unpacked'
            new.response = n if isinstance(n, Mapping) else {subkey : n}
            new.level = dbnode.level + 1
            new.querystatus = dbnode.querystatus
            new.querytime = dbnode.querytime
            new.querytype = dbnode.querytype
            new.queryparams = dbnode.queryparams
            newnodes.append(new)

        self.model.database.session.add_all(newnodes)
        self._childcountall += len(newnodes)
        dbnode.childcount += len(newnodes)
        self.model.database.session.commit()
        self.model.layoutChanged.emit()

    def __repr__(self):
        return self.id

class TreeModel(QAbstractItemModel):
    def __init__(self, database, parent=None):
        super(TreeModel, self).__init__(parent)

        self.database = database
        self.customcolumns = []
        self.newnodes = 0
        self.nodecounter = 0

        #Hidden root
        self.rootItem = TreeItem(self)

    def clear(self):
        self.beginResetModel()
        try:
            self.rootItem.clear()
        finally:
            self.endResetModel()

    def setCustomColumns(self,cols):
        self.customcolumns = cols
        self.layoutChanged.emit()

    def deleteNode(self, index, delaycommit=False):
        if (not self.database.connected) or (not index.isValid()) or (index.column() != 0):
            return False

        self.beginRemoveRows(index.parent(), index.row(), index.row())
        item = index.internalPointer()

        Node.query.filter(Node.id == item.id).delete()
        self.newnodes += 1
        self.commitNewNodes(delaycommit)
        item.remove(True)
        self.endRemoveRows()

    def addNodes(self, nodesdata, extended = False):

        try:
            if not self.database.connected:
                return False

            newnodes = []
            for nodedata in nodesdata:
                if extended:
                    nodedata = nodedata.split('|',1)
                else:
                    nodedata = [nodedata]

                objectid = nodedata[0]
                try:
                  response = json.loads(nodedata[1]) if len(nodedata) > 1 else None
                except:
                    response = None

                new = Node(objectid)
                if isinstance(response,  Mapping):
                    new.response = response

                newnodes.append(new)

            self.database.session.add_all(newnodes)
            self.database.session.commit()
            self.rootItem._childcountall += len(nodesdata)

            self.layoutChanged.emit()
        except Exception as e:
            QMessageBox.critical(self, "Facepager", str(e))

    def commitNewNodes(self, delaycommit=False):
        if (not delaycommit and self.newnodes > 0) or (self.newnodes > 500):
            self.database.session.commit()
            self.newnodes = 0
        if not delaycommit:
            self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            parentNode = self.rootItem
        else:
            parentNode = parent.internalPointer()

        return parentNode.childCount()

    def columnCount(self, parent):
        return 5 + len(self.customcolumns)

    def data(self, index, role):
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.DisplayRole:
            if index.column() == 0:
                return item.data.get('objectid','')
            elif index.column() == 1:
                return item.data.get('objecttype','')
            elif index.column() == 2:
                return item.data.get('querystatus','')
            elif index.column() == 3:
                return item.data.get('querytime','')
            elif index.column() == 4:
                return item.data.get('querytype','')
            else:
                return getDictValue(item.data.get('response',''), self.customcolumns[index.column() - 5])

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            # parent is not valid when it is the root node, since the "parent"
            # method returns an empty QModelIndex
            parentNode = self.rootItem
        else:
            parentNode = parent.internalPointer()  # the node

        childItem = parentNode.child(row)

        return self.createIndex(row, column, childItem)

    def parent(self, index):
        node = index.internalPointer()

        parentNode = node.parent()

        if parentNode == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentNode.row(), 0, parentNode)

    # def flags(self, index):
    #
    #     # Original, inherited flags:
    #     original_flags = super(TreeModel, self).flags(index)
    #
    #     return (original_flags | Qt.ItemIsEnabled
    #             | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
    #             | Qt.ItemIsDropEnabled)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            captions = ['Object ID', 'Object Type', 'Query Status', 'Query Time', 'Query Type'] + self.customcolumns
            return captions[section] if section < len(captions) else ""

        return None

    def getRowHeader(self):
        row = ["id", "parent_id", "level", "object_id", "object_type", "query_status", "query_time", "query_type"]
        for key in self.customcolumns:
            row.append(str(key))
        return row

    def getRowData(self, index):
        node = index.internalPointer()
        row = [node.id,
               node.parentItem.id,
               node.data['level'],
               node.data['objectid'],
               node.data['objecttype'],
               node.data['querystatus'],
               node.data['querytime'],
               node.data['querytype']
              ]
        for key in self.customcolumns:
            row.append(getDictValue(node.data['response'], key))
        return row

    def hasChildren(self, index):
        if not self.database.connected:
            return False

        if not index.isValid():
            item = self.rootItem
        else:
            item = index.internalPointer()

        return item.childCountAll() > 0

    def getItemData(self, item):
        itemdata = {'level': item.level,
                    'objectid': item.objectid,
                    'objecttype': item.objecttype,
                    'querystatus': item.querystatus,
                    'querytime': item.querytime,
                    'querytype': item.querytype,
                    'queryparams': item.queryparams,
                    'response': item.response}
        return itemdata

    def canFetchMore(self, index):
        if not self.database.connected:
            return False

        if not index.isValid():
            item = self.rootItem
        else:
            item = index.internalPointer()

        return item.childCountAll() > item.childCount()

    def fetchMore(self, index):
        if not index.isValid():
            parentItem = self.rootItem
        else:
            parentItem = index.internalPointer()

        if parentItem.childCountAll() == parentItem.childCount():
            return False

        row = parentItem.childCount()
        items = Node.query.filter(Node.parent_id == parentItem.id).offset(row).all()

        self.beginInsertRows(index, row, row + len(items) - 1)

        for item in items:
            itemdata = self.getItemData(item)
            new = TreeItem(self, parentItem, item.id, itemdata)
            new._childcountall = item.childcount
            new._childcountallloaded = True


        self.endInsertRows()
        parentItem.loaded = parentItem.childCountAll() == parentItem.childCount()
