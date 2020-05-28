# @group(Utility)

class Flyweight:

	@classmethod
	def Recycle( cls, value ):
		cls.POOL.append(value)

	@classmethod
	def Create( cls ):
		return cls.POOL.pop() if cls.POOL else cls()

	def init( self ):
		return self

	def reset( self ):
		return self

	def recycle( self ):
		self.reset()
		self.__class__.POOL.append(self)

def unquote( text:bytes ) -> bytes:
	text = text.strip() if text else text
	if not text:
		return text
	if text[0] == text[-1] and text[0] in b"\"'":
		return text[1:-1]
	else:
		return text

# EOF
