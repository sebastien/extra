from extra import Service, Request, Response, on, serve
from extra.feature.files import FileService

__doc__ = """\
An example of a development web server where local filesystem assets are
served with a live transformation phase.
"""

class DevServer(FileService):

	def processECMAScript( self ):
		pass

# NOTE: You can start this with `uvicorn helloworld:app`
app = serve(DevServer)
# EOF
