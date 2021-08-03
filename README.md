# Pastebot
This is a telegram bot forked from a friend of mine, as he wasn't interested in developing it anymore.
It supports nearly every way files can send on telegram! (If not, please open an issue and I will try to add support for it!)
Just send any type of file to the bot or use the /text command to upload stuff to your webserver! The bot will then reply with a url to your file. The filename will be random.

# Table of Contents  
- [Pastebot](#pastebot)
- [Table of Contents](#table-of-contents)
- [Installation](#installation)
  - [Python](#python)
  - [Telegram Side](#telegram-side)
  - [Locally hosted bot server](#locally-hosted-bot-server)
  - [.env](#env)
  - [Service File](#service-file)
  - [NGINX config](#nginx-config)
- [Usage / Commands](#usage--commands)
- [Supported message types](#supported-message-types)


# Installation

## Python
 - **Python 3** (Tested with **3.8.10**)
 - Venv
     - ```bash
        python -m venv pastebot
        source pastebot/bin/activate
        pip install python-telegram-bot
        ```

---

## Telegram Side
1. Go to **BotFather** and create a new bot.
2. Put the token you get into *"TMPBOT_TELEGRAM_TOKEN"* in [.env](.env#L1)
3. Put your telegram-username ***with the @*** into *"TMPBOT_TELEGRAM_WHITELIST"* in [.env](.env#L2)

## Locally hosted bot server
Please take a look at [***this***](https://github.com/tdlib/telegram-bot-api) repository!

---
## .env
```bash
export TMPBOT_TELEGRAM_TOKEN="TELEGRAM_TOKEN" # Your telegram token
export TMPBOT_TELEGRAM_WHITELIST="USERNAME_WHITELIST" # Separated by ":", example: "username1:username2:username3"; WITHOUT @-symbol!
export TMPBOT_PASTE_URL="https://tmp.example.com" # URL where you host the files. This is where you can access the uploaded content.
export TMPBOT_PASTE_DIR="tmp" # Relative path to folder where content will be saved. Example: if value is "tmp", files will be located in a folder called 'tmp' in the same directory as the bot.py file
export TMPBOT_BOT_NAME="MY_BOT" # This has not to be the same as the name specified by BotFather!
# export TMPBOT_DEL_ALL="" # Password used with /delete command to delete all hosted files (Usage: /delete <PASSWORD>). Will not delete index.php file in case you have a file listing script in there.
# export TMPBOT_BASE_URL="http://127.0.0.1:8081/bot" # Only specify if using local bot server.
# export TMPBOT_TIMEOUT="120" # For bigger files, this timeout must be specified because of the communication speed between telegram and the bot-server in case of using a locally hosted server because of network timeout issues.
export TMPBOT_GENERATE_LENGTH="20" # How long the random filename should be
export TMPBOT_GENERATE_TRIES="20" # How often the script should try to generate a random filename until it throws a exception
```

---

## Service File
I recommend creating a user for the bot.
```
[Unit]
Description=Pastebot
; Requires=pastebot-telegram-server.service # Uncomment if you use self hosted telegram-bot-server (Change the service name accordingly)

[Service]
User=pastebot # Change to the user you set up for the bot
Group=pastebot # Same as 'User'
WorkingDirectory=/path/to/cloned-folder
ExecStart=/path/to/cloned-folder/start.sh

[Install]
WantedBy=multi-user.target
```
---

## NGINX config
This config will have some rules only to execute the index.php in the root path, so that you can use a index.php to for example list all your files. I recommend [file-directory-list by halgatewood](https://github.com/halgatewood/file-directory-list/). Remember to change the php-fpm to the installed version number!
```nginx
server {
    server_name "tmp.example.com";
    root /path/to/pastebot/tmp-folder;

    location / {
		try_files $uri $uri.html $uri/ @extensionless-php @not-found;
		index index.php;
	}

    location ~ ^/index.php$ {
		include snippets/fastcgi-php.conf;

		# With php-fpm (or other unix sockets):
		fastcgi_pass unix:/var/run/php/php7.x-fpm.sock; # change to your php socket
		# With php-cgi (or other tcp sockets):
		#	fastcgi_pass 127.0.0.1:9000;
	}

    location ~ \.php$ {
        types { } default_type "text/plain; charset=utf-8";
    }

    location @not-found {
        return 302 /;
    }

    location @extensionless-php {
        rewrite ^(.*)$ $1.php last;
    }

    server_tokens off;
}
```

# Usage / Commands
Here you can find the command usage of the bot.

- **/help** - Displays the help for the bot.
- **/extension** - Sets the file-extension for the next file you upload.
- **/text** - Saves the text as .txt-file
  - Usage:
    ```
    /text
    Lorem ipsum dolor sit amet, consetetur sadipscing
    elitr, sed diam nonumy eirmod tempor invidunt ut 
    labore et dolore magna aliquyam erat, sed diam 
    voluptua. At vero eos et accusam et
    ```
- **/debug** - Only works for the first user defined in *'TMPBOT_TELEGRAM_WHITELIST'*. Prints all arrays containing stuff like infos for the long-text-routines.
- **/delete** - Only works for the first user defined in *'TMPBOT_TELEGRAM_WHITELIST'*.
  - Usage: `/delete MY_SECURE_PASSWORD`
  - All messages containing `/delete` will delete themselves after a little delay.

# Supported message types
The default file extension is the extension that will be used in case file extension can't be found using MIME.
This list is build like this: **Type** -> *Default file extension*
- Text message -> .txt
- Images -> .jpg
- Documents -> .txt
- Audio files -> .mp3
- Voice messages -> .voice
- Video files -> .video
- Contacts (.vcf / vCard / **text/vCard**) -> .vcf
- Video-Notes -> .mp4
- Sticker -> .webp for normal sticker / .tgs for animated sticker