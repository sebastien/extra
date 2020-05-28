from extra.protocol.http import HTTPRequest

# curl -X POST -H "Content-Type: text/html; charset=UTF-8" --data-ascii "content=derinhält&date=asdf" http://localhost:8000/
HTTPRequest().bodyFromStream(stream, "application/x-www-form-urlencoded")
# EOF
