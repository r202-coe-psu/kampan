from kampan import worker


def main():
    server = worker.create_server()
    server.run()
