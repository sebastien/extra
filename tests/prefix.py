from extra.routing import Prefix

prefix = Prefix.Make((
	"post",
	"post/",
	"post/pouet",
	"post/something-like-that",
	"post/query",
	"posts/query",
))
print (str(prefix))
print (str(prefix.simplify()))

