from txp_parser import export_sprites_to_png
import os,sys


if __name__ == "__main__":
    usedir=sys.argv[1]
    print(usedir)
    for file in os.listdir(usedir):
        if not file.endswith(".farc"):
            continue
        print(file)
        full=os.path.join(usedir,file)
        dirname=os.path.join("testfiles","extracted_"+file)
        export_sprites_to_png(full,dirname)