from txp_parser import SpriteSet_from_file
import os,sys
from config import batch_export_skip as skip




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
            
            full=os.path.join(root,file)

            use_skip=False
            for name in skip:
                if name in full:
                    use_skip=True
                    break
            if use_skip:
                continue

            sprite_img=None 
            print(f"start extracting {full}")                                                                                                                        
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
           
