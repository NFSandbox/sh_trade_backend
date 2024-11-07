import uvicorn
import subprocess

from config import general as gene_conf

# Start uvicorn server
if __name__ == "__main__":
    # try start the supertokens server
    subprocess.run(
        f"supertokens start --host {gene_conf.ST_HOST} --port {gene_conf.ST_PORT}",
        shell=True,
    )

    # start uvicorn server with directory monitor
    uvicorn.run(
        app="main:app",
        # here in some VPS 127.0.0.1 won't work, need to use 0.0.0.0 instead
        host=gene_conf.HOST,
        port=gene_conf.PORT,
        reload=True,
        # hide uvicorn header
        server_header=False,
    )
