Thumbnails
Thumbnails are a sprite exclusive to the Mega Mix UI. They can be tricky at first, but simple once you get a hang of it and have a proper system set-up (which this guide has tried to do for you). Thumbnail sprites should always use the same exact art as your jacket, just like official SEGA sheets. But you’re still free to scale, rotate, and position the jackets however you like. Players who tend to be more visual may recall a song based on its jacket, so not using the same art will throw them off and potentially make it harder to find your song.

SEGA typically compiles thumbnails for multiple songs into one sprite sheet. There are four different size sprite sheets that you can see in spr_sel_pvtmb.farc from rom_steam of diva_main.cpk:
A 512 x 128 thumbnail sheet containing 3 thumbnails:

A 512 x 256 thumbnail sheet containing 9 thumbnails:

A 512 x 512 thumbnail sheet containing 21 thumbnails:

A 2048 x 1024 thumbnail sheet containing 225 thumbnails:

You should choose a sprite sheet size based on your needs. You can also create a single thumbnail sprite sheet, which I have included in the Song Mod Resources.

You also have the option of creating your own sprite sheets. Keep in mind that they should still be spaced similarly to SEGA’s sprite sheets, and that the resolutions must follow a power of 2 (2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, etc). Sprite coordinate calculations in subsequent sections of the guide will be based off of SEGA’s sprite sheet layouts.

Just like with the other sprite sheets, the Song Mod Resources folder contains template .PSD files and layer masks to help you arrange your sprites. Each individual sprite is separated into different folders to help you keep things separate. To help mimic SEGA’s sprites, put your sprite in the Image Mask (Place Images Inside Here) folder for each thumbnail. There are templates I made for the 1, 3, 9, 21, and 225 thumbnail variants, with each template being based on game assets.

Thumbnails (spr_sel_pvtmb_mod_name.farc)
Before editing spr_sel_pvtmb_mod_name.farc, go ahead and rename it based on your mod’s name. Remember to replace any spaces with _ and remove any special characters. For example, lavverso Song Pack would use spr_sel_pvtmb_lavverso_song_pack.farc. Megpoid the Music# Song Pack would use spr_sel_pvtmb_megpoid_the_music#_song_pack.farc.

When you open the file in Miku Miku Model, it should look like this:

Firstly, remember to change the name of your .bin to match the .farc file name (excluding the extension, of course).

Each individual thumbnail sprite represents a different PV. It’s name should match the PV ID that it’s for. Therefore, change #### to your song’s PV ID (eg. 6916).

Texture Index: The index of the sprite sheet the thumbnail comes from. (MERGE_D5COMP_0 is 0, MERGE_D5COMP_1 is 1, etc.)
X Position: 2 minimum (2 is for the first thumbnail in a row; See below for more information)
Y Position: 2 minimum (2 is for the first thumbnail in a column; See below for more information)
Width: Always 128 pixels
Height: Always 64 pixels
Name: This will always be your PV ID.
If you haven’t noticed, the template .PSD files have each thumbnail separated into individual folders. Each folder’s name specifies the X and Y coordinates you need to put into Miku Miku Model. However, if you don’t want to rely on the .PSD files, there’s some simple math you can do:
For each sprite’s X position, perform 2 + (132 * x), where x is equal to how many sprites are in front of it.
For each sprite’s Y position, perform 2 + (68 * y), where y is equal to how many sprites are on top of it.

If you have more than one song in your mod, you can add more thumbnails by right clicking the .bin file and picking “Add dummy sprite”. Remember to update all of your values accordingly.



Adding a dummy sprite will default your Resolution mode to HDTV720. Remember to change this to HDTV1080. Also remember that if you’re adding a new sprite sheet, check that your Texture index is pointing to the correct texture. Miku Miku Model should give you an accurate preview of what the game is going to interpret your sprite as.


You can do the same with sprite sheets by right clicking “Texture Set” and choosing “Import” (or Ctrl + I). Remember to rename the texture accordingly (a second texture would be MERGE_D5COMP_1, a third texture would be MERGE_D5COMP_2, and so-on).

When you’re done, save and make sure your file name is correct.
