# turo-emails-to-ics

Configure postfix to run the script when your addresses match (here calsync@)

# /etc/postfix/main.cf
```
# ensure that you have the correct permissions set up to allow Postfix to call external programs. 
# Look for the default_privs parameter, which specifies as which user the external commands should be executed. This is important for security
default_privs = <someuser>
```

# /etc/aliases
```
calsync: "|/usr/bin/python3 /opt/calsync.py"
```
