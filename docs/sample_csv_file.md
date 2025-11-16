# About
This documentation guides you how to create a **CSV** file for adding songs to your *library*.

# Location of CSV file
If you are manually creating your CSV file then save it under [library](/my-player/my_player/data/library/) path.

You can also add new category / songs from the player using "➕ Add/Append Category" button.

# Syntax

## CSV header
```
Song,Film/Album,Artists
```
## song having one artist
```
<song name>,<film/album name>,<artist name>
```
## song having more than one artist
```
<song name>,<film/album name>,"<artist1 name>, <artist2 name>"
```
## song or film/album having a comma in its name
```
"<song name with ,>","<film/album name with ,>",<artist name>
```
