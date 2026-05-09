function main(arg1) {
    var posList = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f, 0x28, 0x1b, 0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8, 0xe, 0x15, 0x20, 0x1a, 0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c, 0x22, 0x25, 0xc, 0x24];
    var mask = '3000176000856006061501533003690027800375';
    var outPutList = [];
    for (var i = 0; i < arg1.length; i++) {
        var this_i = arg1[i];
        for (var j = 0; j < posList.length; j++) {
            if (posList[j] == i + 1) {
                outPutList[j] = this_i;
            }
        }
    }
    var arg2 = outPutList.join('');
    var arg3 = '';
    for (var i = 0; i < arg2.length && i < mask.length; i += 2) {
        var strChar = parseInt(arg2.substr(i, 2), 16);
        var maskChar = parseInt(mask.substr(i, 2), 16);
        var xorChar = (strChar ^ maskChar).toString(16);

        if (xorChar.length == 1) {
            xorChar = '0' + xorChar;
        }
        arg3 += xorChar;
    }
    return arg3;
}
