from kampan import controllers


def main():
    server = controllers.create_server()
    server.run()
