# select pyqt api 2

def useQt():
	try:
		__import__("sip") # append an x to force not using Qt
	except ImportError:
		return False
	else:
		return True

if useQt():
	import sip
	API_NAMES = ["QDate", "QDateTime", "QString", "QTextStream", "QTime", "QUrl", "QVariant"]
	API_VERSION = 2
	for name in API_NAMES:
		sip.setapi(name, API_VERSION)

	from PyQt4.QtCore import *
	from PyQt4.QtGui import *
	from PyQt4.QtSvg import *
	from PyQt4.QtCore import pyqtSignal as Signal
	from PyQt4.QtCore import pyqtSlot as Slot
	from PyQt4 import QtCore
else:
	from machines import *
