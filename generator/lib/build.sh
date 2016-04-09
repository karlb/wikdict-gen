OS=${OSTYPE//[0-9.]/}
if [ "$OS" == "darwin" ]; then
	gcc -g -fPIC -dynamiclib spellfix.c -o spellfix1.dylib
	gcc -g -fPIC -dynamiclib fts5.c -o fts5.dylib
else
	gcc -g -fPIC -shared spellfix.c -o spellfix1.so
	gcc -g -fPIC -shared fts5.c -o fts5.so
fi
