from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import QFileDialog, QCheckBox, QComboBox, QLabel, QHBoxLayout
import csv
from progressbar import ProgressBar
import codecs
from pandas import merge,read_csv

from database import *

class ExportFileDialog(QFileDialog):
    """
    Create a custom Export-File Dialog with options like BOM etc.
    """

    def __init__(self,*args,**kwargs):
        super(ExportFileDialog,self).__init__(*args,**kwargs)

        self.mainWindow = self.parent()
        self.setWindowTitle("Export nodes to CSV")
        self.setAcceptMode(QFileDialog.AcceptSave)
        self.setOption(QFileDialog.DontUseNativeDialog)
        #self.setFilter("CSV Files (*.csv)")
        self.setDefaultSuffix("csv")

        self.optionBOM = QCheckBox("Use a BOM",self)
        self.optionBOM.setCheckState(Qt.CheckState.Checked)

        self.optionLinebreaks = QCheckBox("Remove line breaks",self)
        self.optionLinebreaks.setCheckState(Qt.CheckState.Checked)

        self.optionSeparator = QComboBox(self)
        self.optionSeparator.insertItems(0, [";","\\t",","])
        self.optionSeparator.setEditable(True)

        #self.optionLinebreaks.setCheckState(Qt.CheckState.Checked)

        self.optionWide = QCheckBox("Convert to wide format (experimental feature)",self)
        self.optionWide.setCheckState(Qt.CheckState.Unchecked)

        # if none or all are selected, export all
        # if one or more are selected, export selective
        self.optionAll = QComboBox(self)
        self.optionAll.insertItems(0, ['All nodes (faster for large datasets, ordered by internal ID)','Selected nodes (ordered like shown in nodes view)'])
        if self.mainWindow.tree.noneOrAllSelected():
            self.optionAll.setCurrentIndex(0)
        else:
            self.optionAll.setCurrentIndex(1)

        layout = self.layout()
        row = layout.rowCount()
        layout.addWidget(QLabel('Options'),row,0)

        options = QHBoxLayout()
        options.addWidget(self.optionBOM)
        options.addWidget(self.optionLinebreaks)
        options.addWidget(QLabel('Separator'))
        options.addWidget(self.optionSeparator)
        options.addStretch(1)

        layout.addLayout(options,row,1,1,2)

        layout.addWidget(QLabel('Post processing'),row+1,0)
        layout.addWidget(self.optionWide,row+1,1,1,2)

        layout.addWidget(QLabel('Export mode'),row+2,0)
        layout.addWidget(self.optionAll,row+2,1,1,2)
        self.setLayout(layout)

        if self.exec_():

            if os.path.isfile(self.selectedFiles()[0]):
                os.remove(self.selectedFiles()[0])
            output = open(self.selectedFiles()[0], 'w', newline='', encoding='utf8')
            if self.optionBOM.isChecked() and not self.optionWide.isChecked():
                output.write('\ufeff')

            try:
                if self.optionAll.currentIndex() == 0:
                    self.exportAllNodes(output)
                else:
                    self.exportSelectedNodes(output)
            finally:
                output.close()

            if self.optionWide.isChecked():
                self.convertToWideFormat(self.selectedFiles()[0])


    def exportSelectedNodes(self,output):
        progress = ProgressBar("Exporting data...", self.mainWindow)

        #indexes = self.mainWindow.tree.selectionModel().selectedRows()
        #if child nodes should be exported as well, uncomment this line an comment the previous one
        indexes = self.mainWindow.tree.selectedIndexesAndChildren()
        indexes = list(indexes)
        progress.setMaximum(len(indexes))

        try:
            delimiter = self.optionSeparator.currentText()
            delimiter = delimiter.encode('utf-8').decode('unicode_escape')
            writer = csv.writer(output, delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_ALL, doublequote=True,
                                lineterminator='\r\n')


            #headers
            row = [str(val) for val in self.mainWindow.tree.treemodel.getRowHeader()]
            if self.optionLinebreaks.isChecked():
                row = [val.replace('\n', ' ').replace('\r',' ') for val in row]

            writer.writerow(row)

            #rows
            for no in range(len(indexes)):
                if progress.wasCanceled:
                    break

                row = [str(val) for val in self.mainWindow.tree.treemodel.getRowData(indexes[no])]
                if self.optionLinebreaks.isChecked():
                    row = [val.replace('\n', ' ').replace('\r',' ') for val in row]

                writer.writerow(row)

                progress.step()

        finally:
            progress.close()


    def exportAllNodes(self,output):
        progress = ProgressBar("Exporting data...", self.mainWindow)
        progress.setMaximum(Node.query.count())


        try:
            delimiter = self.optionSeparator.currentText()
            delimiter = delimiter.encode('utf-8').decode('unicode_escape')
            writer = csv.writer(output, delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_ALL, doublequote=True,
                                lineterminator='\r\n')

            #headers
            row = ["level", "id", "parent_id", "object_id", "object_type", "query_status", "query_time",
                   "query_type"]
            for key in self.mainWindow.tree.treemodel.customcolumns:
                row.append(key)
            if self.optionLinebreaks.isChecked():
                row = [val.replace('\n', ' ').replace('\r',' ') for val in row]

            writer.writerow(row)

            #rows
            page = 0

            while True:
                allnodes = Node.query.offset(page * 5000).limit(5000)
                if allnodes.count() == 0:
                    break
                for node in allnodes:
                    if progress.wasCanceled:
                        break
                    row = [node.level, node.id, node.parent_id, node.objectid, node.objecttype,
                           node.querystatus, node.querytime, node.querytype]
                    for key in self.mainWindow.tree.treemodel.customcolumns:
                        row.append(node.getResponseValue(key))

                    if self.optionLinebreaks.isChecked():
                        row = [str(val).replace('\n', ' ').replace('\r',' ') for val in row]

                    writer.writerow(row)
                    # step the Bar
                    progress.step()
                if progress.wasCanceled:
                    break
                else:
                    page += 1

        finally:
            progress.close()

    def convertToWideFormat(self,filename):
        progress = ProgressBar("Converting data...", self.mainWindow)
        try:
            #Separate levels
            def flattenTable(fulltable,levelcol,idcol,parentidcol,countchildren,removeempty):
                fulltable[[levelcol]] = fulltable[[levelcol]].astype(int)

                levels = dict(list(fulltable.groupby(levelcol)))
                minlevel = fulltable.level.min()
                for level, data in sorted(levels.items()):
                    #First level is the starting point for the following merges
                    if level == minlevel:
                        #data = data[[idcol,'object_id','object_type']]
                        data = data.add_prefix('level_{}-'.format(level))
                        flattable = data
                    else:
                        #Aggregate object types and join them
                        for col_countchildren in countchildren:
                            children = data[parentidcol].groupby([data[parentidcol],data[col_countchildren]]).count()
                            children = children.unstack(col_countchildren)
                            children['total'] = children.sum(axis=1)
                            children = children.add_prefix('level_{}-children-{}-'.format(level-1,col_countchildren))

                            leftkey = 'level_{}-id'.format(level-1)
                            flattable = merge(flattable,children,how='left',left_on=leftkey,right_index=True)
                            flattable[children.columns.values.tolist()] = flattable[children.columns.values.tolist()].fillna(0).astype(int)

                        #Join data
                        data['childnumber'] = data.groupby(parentidcol).cumcount()
                        leftkey = 'level_{}-{}'.format(level-1,idcol)
                        rightkey = 'level_{}-{}'.format(level,parentidcol)
                        data = data.drop([levelcol],axis=1)
                        data = data.add_prefix('level_{}-'.format(level))
                        flattable = merge(flattable,data,how="outer",left_on=leftkey,right_on=rightkey)

                if removeempty:
                    flattable = flattable.dropna(axis=1,how='all')
                return flattable

            try:
                #delimiter
                delimiter = self.optionSeparator.currentText()
                delimiter = delimiter.encode('utf-8').decode('unicode_escape')

                #open
                data = read_csv(filename, sep=delimiter,encoding='utf-8',dtype=str)

                #convert
                newdata = flattenTable(data,'level','id','parent_id',['object_type','query_status','query_type'],False)


                #save
                outfile = open(filename, 'w',newline='',encoding='utf8')
                try:
                    if self.optionBOM.isChecked():
                        outfile.write('\ufeff') #UTF8 BOM
                    newdata.to_csv(outfile,sep=delimiter,index=False,encoding="utf-8")
                finally:
                    outfile.close()
            except Exception as e:
                self.mainWindow.logmessage(e)
        finally:
            progress.close()
