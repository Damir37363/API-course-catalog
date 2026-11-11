import sys

from sqlalchemy.orm import Session

from db import engine
from models import Course

# python try_lost_update.py          -> a.likes += 1                (loses a like)
# python try_lost_update.py atomic   -> a.likes = Course.likes + 1  (the database adds)
atomic = "atomic" in sys.argv[1:]

with Session(engine) as alice, Session(engine) as bob:
    a = alice.get(Course, "api-design")
    b = bob.get(Course, "api-design")
    print("Alice reads", a.likes, "| Bob reads", b.likes)
    if atomic:
        a.likes = Course.likes + 1
    else:
        a.likes += 1
    alice.commit()
    if atomic:
        b.likes = Course.likes + 1
    else:
        b.likes += 1
    bob.commit()

with Session(engine) as session:
    print("in the database:", session.get(Course, "api-design").likes)
