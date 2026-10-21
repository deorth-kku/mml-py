from txp_parser import SpriteSet_from_file
import os,sys
import re


def findpv(file:str)->str:
    file=file.replace(".","_")
    for part in file.split("_"):
        if part.startswith("pv"):
            return part
    return None

if __name__ == "__main__":
    usedir=sys.argv[1]                                                                                                                                                                                                                                              
    for root, dirs, files in os.walk(usedir):
        for file in files:
            if not file.endswith(".farc"):
                continue
            pv=findpv(file)
            if pv==None:
                print(f"cannot find pv name in {file}")
                continue
            elif pv=="pvtmb":
                continue
            
            full=os.path.join(root,file)
            sprite_img=None                                                                                                                         
            for sprite,img in SpriteSet_from_file(full):
                if "JK" in sprite.name:                                               
                    sprite_img=img
                    break
            if sprite_img==None:
                print(f"cannot file cover in {full}")
                continue
            
            
            png=os.path.join("testfiles",pv+".png")
            sprite_img.save(png)
            print(f"saved png {png}")
           
