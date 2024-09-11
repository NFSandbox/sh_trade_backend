You can follow this guide to deploy the backend of AHU Elec Watch.

# Python Environment

## Install Conda

Here we recommend using `Conda` to quickly build the Python environment for this project. Follow [Conda Installation
Guide](https://conda.io/projects/conda/en/latest/user-guide/install/index.html) to install `Conda` first if it's not on
your server.

## Build Env From Config File

The env configuration is provided as a conda config file `environment.yml` in the root directory.

You could run the following command to create a new conda environment.

```shell
conda env create -f environment.yml
```

## Switch To Target Env

Run the following command to switch to the created env:

```shell
conda activate ahu_elec_watchboard_backend
```

If you want to return to base env, you could run:

```shell
conda activate
```

# Edit Project Configuration

All configuration is in `./config` directory, the example file is provided with naming convention:

```
<config_name>_example.py
```

You need to create a new file without the `_example` subfix in name, then edit the config following the instruction
of the comment or the guide below.

For example, you need to create `auth.py` from `auth_example.py` then modified the content based on your own
configuration.

## AHU Header Credentials & Dorm Info

Prerequisites:

- WeChat Desktop
- A web browser with DevTools _(Chrome, Edges etc.)_

First we need to configure `ahu_header.json`, which will be used as credentials in cookies when accessing and
retrieving info from AHU website.

Open WeChat AHU Mini Program, open Electrical Bill Top Up page. Then click "Open In Browser".

![image](https://github.com/user-attachments/assets/4cf93c1f-ac10-4e76-8642-0992033bdc03)

Then **press `F12` to open Dev Tools** of the browser, and **switch to "Network" panel**.

![image](https://github.com/user-attachments/assets/4a60dc3c-f777-4590-9bbd-0b7983419192)

Now, start to select your own **campus region, dormitory and room number** until you can **see your account balance**.

Then check out the "Network" panel, select the newest network request to `getThirdData` path, click the "PayLoad"
section. Then you will see the info you need.

![image](https://github.com/user-attachments/assets/22d83ea5-5f2c-4215-a8ba-33fa41eaed49)

> You may need to repeat the above operation twice time to get both "Illumination" and "Air Conditioner" info.
> 
> - `DORM_LIGHT_INFO_DICT` is used to retrieve illumination fee.
> - `DORM_AC_INFO_DICT` is used to retrieve air conditioner fee.

Then fill the `DORM_LIGHT_INFO_DICT` and `DORM_AC_INFO_DICT` in `config/dorm.py` based on the info you get.

## JWT Secret Key

You need to generate your own `PYJWT_SECRET_KEY` in `config/auth.py`. You may use `secrets` package to generate a
valid token.

```python
import secrets

print(secrets.token_hex(20))
```

![image](https://github.com/user-attachments/assets/afc90aaa-efac-4a8e-883a-4c0f8119cb02)

> Keep your secret key private at anytime.

-----

For other files or fields not mentioned above, you can follow the comment inside the example file.

## Initialize Database

Run following command to initailize the database:

```shell
python create_db.py
```

> Notice: Make sure you have **correctly configured `config/sql.py` before initializing database**. 
> Otherwise the Python script would not be able to connect to the correct database.

## TODO: One-step Configuration Extraction From AHU Website URL

> This feature is not available for now, but may be added to this project in the future.

Since all the info required above like `AHU Credential` and `Dormitory Configuration` info etc are all contained in the URL of AHU Website, 
it's possible for **users to only provide a personal link to program and leave all other things to the program**.

# Catch Records From AHU Website

You could execute `catch_records.py` to catch a record from AHU website and add it to database.

```shell
python catch_records.py
```

Here **recommend using something like `cron` to automatically catch records** (for example every 30th minutes of an hours)

If you are using `cron` with shell script, you need to **first activate the corresponding `Conda` env** before executing
the Python script. Below is an example of the shell script.

```shell
source /root/anaconda3/bin/activate ahu_elec_watchboard_backend
cd /home/code_project/ahu_elec_watch_backend
python catch_record.py
```

> Notice: You may need to **replace to your own conda binary file path and your own project root directory path** in above script.

For how to use `cron`, check out [Linux Cron Jobs - FreeCodeCamp](https://www.freecodecamp.org/news/cron-jobs-in-linux/)

# Start FastAPI Server

Now all you need to do is to start the server:

```shell
python main.py
```

You can consider using Nginx Reverse Proxy or other method to enable access through domain name and enable HTTPS to your backend services.