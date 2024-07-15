from extra.handler import request

event = {
    "requestContext": {
        "elb": {
            "targetGroupArn": "arn:aws:elasticloadbalancing:RRRRRRRRRRRRRR:000000000000:targetgroup/NNNNNNNNNNNNNNNNNNNNNNN-XXXXXXX/XXXXXXXXXXXXXXXX"
        }
    },
    "httpMethod": "GET",
    "path": "/do/hook/update-retractions",
    "queryStringParameters": {},
    "headers": {
        "accept-encoding": "gzip",
        "akamai-origin-hop": "2",
        "authorization": "Bearer XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "cache-control": "no-cache, max-age=0",
        "connection": "keep-alive",
        "host": "nnnnnnnnnnnnn.nnn.nnn",
        "pragma": "no-cache",
        "te": "chunked;q=1.0",
        "true-client-ip": "103.103.41.59",
        "via": "1.1 v1-akamaitech.net(ghost) (AkamaiGHost), 1.1 akamai.net(ghost) (AkamaiGHost)",
        "x-akamai-config-log-detail": "true",
        "x-amzn-trace-id": "Root=N-NNNNNNNN-NNNNNNNNNNNNNNNNNNNNNNNN",
        "x-forwarded-for": "XXX.XXX.XXX.XXX, XXX.XXX.XXX.XXX",
        "x-forwarded-port": "443",
        "x-forwarded-proto": "https",
    },
    "body": "",
    "isBase64Encoded": False,
}

req = request(event)
assert req.method == "GET"
assert req.path == "/do/hook/update-retractions"
for k, v in event["headers"].items():
    assert req.getHeader(k) == v
# EOF
