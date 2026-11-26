// TASK-268: Math.sin / Math.cos exactly as Chromium computes them, for the node portal harness (harness.mjs
// makePortalWorld). Chromium's V8 (14.x, Chrome 148 here) is built with V8_USE_LIBM_TRIG_FUNCTIONS: its sin/cos
// are glibc's IBM Accurate Mathematical Library routines (v8/third_party/glibc/src/sysdeps/ieee754/dbl-64/s_sin.c,
// sincostab.c, usncs.h; branch-heads/14.8, glibc revision 4e21c2075193e406a92c0d1cb091a7c804fda4d9), while node's V8
// (12/20/24) uses the fdlibm ports, which differ in the last bit for ~3 % of arguments. That last bit changed a
// teleport's exit velocity (portalTeleport's cos/sin of the rotation angle) and portal frames, so the node run
// drifted from the game. This is a line-by-line JavaScript port of glibc_sin / glibc_cos for |x| < 105414350
// (all JS double arithmetic is IEEE round-to-nearest without FMA, like the x86-64 baseline build), which covers every
// angle the physics passes (portal angles and their differences, |x| < 10). Larger finite |x| would need __branred
// and throws. Every other Math function physics uses (atan2, hypot, sqrt, pow) is identical between node and Chromium
// (checked by tests/physics/portal_parity.mjs --math-check).
//
// IBM Accurate Mathematical Library, Copyright (C) 2001-2022 Free Software Foundation, Inc. -- GNU LGPL 2.1 or later.
var GlibcSinCos = (function ()
{
    const TAB_HEX =
    '000000000000000000000000000000003ff000000000000000000000000000003f7fffeaaaaeeeefbc1e45e2ec67b77c3fefffc000155552' +
    '3c8f4a01a0196dae3f8fffaaaaeeeed5bc02ab639a9f07773fefff000155549f3c828a28a03a5ef33f97ff70010332553bfefe2b51527336' +
    '3feffdc006bff7e63c8ae6dae86977bd3f9ffeaaaeeee86fbc3cd406fb224ae23feffc00155527d3bc83b54492d89b5b3fa3feb2b12d45d5' +
    '3c34ec54203d1c113feff9c03414a7ba3c6991f4be6c59bf3fa7fdc01032fba9bc4599bdf46e997a3feff7006bfdf99fbc78b3b560648d5f' +
    '3fabfc6d78586dac3c18e4fd03dbf2363feff3c0c8103a313c74856dbddc0e663faffaaaeeed4edbbc42d16d32684b693feff0015549f4d3' +
    '3c8328387b99426f3fb1fc343d808befbc5f3d32e6f3be4f3fefebc222a8ef9f3c57934934f54c773fb3facb12d1755bbc5921915299468c' +
    '3fefe7034129ef6fbc6cbf4337c96f973fb5f911fd10b737bc50184f02be91023fefe1c4c3c873ebbc35a9c9057c4a023fb7f701032550e4' +
    '3c3afc2d1800501a3fefdc06bf7e6b9b3c831902b535f8db3fb9f4902d55d1f93c52696d7eac1dc13fefd5c94b43e000bc62e768cb4f92f9' +
    '3fbbf1b78568391d3c5e91841dea4cc83fefcf0c800e99b13c6ea3d786d186ac3fbdee6f16c1cce6bc450f8e2fb716733fefc7d078d1bc88' +
    '3c8075d2447db6853fbfeaaeee86ee36bc4afcb2bcc6f03b3fefc015527d5bd33c8b68f35094efb83fc0f3378ddd71d13c6d8468724f0f9e' +
    '3fefb7db2bfe06953c821dadf4f65ab13fc1f0d3d7afceafbc66ef95099769a53fefaf22263c4bd3bc552ace133a27693fc2ee285e4ab88f' +
    'bc6e4d0f05dee0583fefa5ea641c36f23c404da6ed17cc7c3fc3eb312c5d66cb3c647d666b66cb913fef9c340a7cc4283c8c5b6b063b7462' +
    '3fc4e7ea4dc5f27b3c5949db2ac072fc3fef91ff40374d01bc67d03f4d3a9e4c3fc5e44fcfa126f3bc66f443063f89b63fef874c2e1eecf6' +
    'bc8c6514e1332b163fc6e05dc05a4d4cbbd32c5c8b81c9403fef7c1afeffde24bc78f55bc47540b13fc7dc102fbaf2b53c45ab50e23c97c3' +
    '3fef706bdf9ece1cbc8698c80c36dcb43fc8d7632efaa944bc620fa262cbb9533fef643efeb82acd3c76b00ac1fe28ac3fc9d252d0cec312' +
    '3c59c43d80b1137d3fef57948cff67973c6e3a0d3e03b1d53fcaccdb297a0765bc59883b57d6cdeb3fef4a6cbd1e3a793c813df0edaebb57' +
    '3fcbc6f84edc61993c69c1a56a7b0cab3fef3cc7c3b3d16ebc621a3ad28a34943fccc0a6588289a3bc6868d09bc87c6b3fef2ea5d753ffed' +
    '3c8cc4215f56d5833fcdb9e15fb5a5d0bc632e20d6cc6fc23fef20073086649f3c7b940416c1984b3fceb2a57f8ae5a3bc60be06af572ceb' +
    '3fef10ec09c5873b3c8d9072762c12833fcfaaeed4f31577bc615d88508e32b83fef01549f7deea13c8d3c1e99e5cafd3fd0515cbf65155c' +
    'bc79b8c29dfd8ec83feef141300d2f26bc82aa1b08ded3723fd0cd00cef36436bc79fb0a0c93e2b53feee0b1fbc0f11cbc4bfd2380bbc3b1' +
    '3fd14861aa94ddebbc6be881b5b615a43feecfa744d5efa1bc556d0a4af541d03fd1c37d64c6b8763c746076fe0dcff53feebe214f76efa8' +
    'bc802f9f12ba543e3fd23e52111aaf36bc74f080334eff183feeac2061bbaf4f3c62c1d53e94658d3fd2b8ddc43eb49f3c61553899f2d807' +
    '3fee99a4c3a7cd83bc82264b1bc53ce83fd3331e94049f873c7e0cb6b40c302c3fee86aebf29a9ed3c89397afdbb58a73fd3ad129769d3d8' +
    '3c003d55048783983fee733ea0193d40bc86428b3546ce133fd426b7e69ee697bc7f09c75705c59f3fee5f54b436e9d03c87eb0fd02fc8bc' +
    '3fd4a00c9b0f3d203c7823ba6bb08ead3fee4af14b2a449cbc868ca02e8a68333fd5190ecf68a77a3c7b357155eef0f33fee3614b680d6a5' +
    'bc727793aa0152373fd591bc9fa2f5973c67c74bac3fe0cb3fee20bf49acd6c1bc5660aec7ef636c3fd60a14290787753c5b1fd80ba89133' +
    '3fee0af15a03dbce3c5fe8e702771ae63fd682138a38d7f7bc7d889202444aad3fedf4ab3ebd875ebc8e2d8a7e6736c43fd6f9b8e33a0255' +
    '3c742bc14ee9da0d3feddded50f228d6bc6e80c8d42ba2bf3fd7710255764214bc66ead7314bb6ce3fedc6b7eb9959123c54b364776dcd35' +
    '3fd7e7ee03c86d4ebc7b63bcdabf5af23fedaf0b6b888e833c8a249e2b5e5cea3fd85e7a128269493c78a40e9b5face03fed96e82f71a9dc' +
    '3c8ff61bd5d2039d3fd8d4a4a774992f3c744a02ea7663263fed7e4e97e17b4abc63b770352bed943fd94a6be9f546c5bc769ce13e683f58' +
    '3fed653f073e4040bc876236434bec373fd9bfce02e805103c709e39a320b0a43fed4bb9e1c619e03c8f34bb77858f613fda34c91cc50cca' +
    'bc5a310e3b50cecd3fed31bf8d8d7c063c7e60dd3089cbdd3fdaa95b63a09277bc66293eb13c03813fed1750727d94f03c80d52b1ec1a48e' +
    '3fdb1d8305321617bc7ae242cb99f5193fecfc6cfa52ad9f3c88b5b5508f2a0d3fdb913e30dbac43bc7e38ad2f6c3ff13fece115909a82e5' +
    '3c81f139bb31109a3fdc048b17b140a33c619fe6757e9fa73fecc54aa2b2972e3c64ee162ba83a983fdc7767ec7fd19ebc5eb14d1a3d5826' +
    '3feca90c9fc67d0bbc646a81485e34623fdce9d2e3d4a51fbc62fc8a12dae2983fec8c5bf8ce1a843c7ab3d1a15901233fdd5bca34047661' +
    '3c728a44a75fc29c3fec6f39208be53bbc8741dbfbaadb423fddcd4c15329c9a3c70d4c6e171fd9a3fec51a48b8b175ebc61bbb43b9aa880' +
    '3fde3e56c1582a69bc50a4821099f88f3fec339eb01ddd81bc8caaf5ee82c5c03fdeaee8744b05f0bc5789b43c9b027d3fec1528065b7d50' +
    'bc8892111312e8283fdf1eff6bc4f97b3c717212f8a7525c3febf641081e75363c8b7bd71628a9a13fdf8e99e76abc973c59d950af2d00a3' +
    '3febd6ea310294f53c731bbcc88c109d3fdffdb628d2f57a3c6f4a992e905b6a3febb723fe630f323c772bd2452d0a393fe0362939c69955' +
    'bc82d8cd78397b013feb96eeef58840e3c545a3cc78fade03fe06d3686946e5b3c83f5ae4538ff1b3feb764b84b704c2bc8f5848c21b389b' +
    '3fe0a4021e9e1001bc86f643a13914f63feb553a410c104e3c58ff7947027a163fe0da8b26b5672ebc8a58def0bee9093feb33bba89c8948' +
    '3c8ea6a51d1f6ca93fe110d0c4b69c3b3c8d9189988099813feb11d04162a4c63c71dd561efbc0c23fe146d21f8b7f823c7bf9535e2739a8' +
    '3feaef78930bd275bc7f836279746f943fe17c8e5f2eedb03c635e57102e24883feaccb526f69de53c88fb6a8dd6b6cc3fe1b204acb02fdd' +
    'bc5f190c70cbb5ff3feaa98688308913bc0b83d607cd50703fe1e7343236574c3c722a3fa4f41d5a3fea85ed4373e02d3c69be06385ec792' +
    '3fe21c1c1b0394cf3c5e5b324b23aa313fea61e9e72586af3c858330e2fd453f3fe250bb93788bbb3c7ea3d02457bcce3fea3d7d0352bdcf' +
    'bc868dbaeca196693fe28511c917a067bc801df1d9a16b703fea18a729aee4453c395e25736c03583fe2b91dea88421ebc8fa371db216ab0' +
    '3fe9f368ed912f85bc81d200c57916063fe2ecdf279a30823c8d3557e0e7e37e3fe9cdc2e3f25e5c3c83f99112993f623fe32054b148bc4f' +
    '3c8f6b42095a135b3fe9a7b5a36a65143c8722cfcc9fa7a93fe3537db9be03673c6b327e7af040f03fe98141c42e13103c8d1ff80488f08d' +
    '3fe386597456282bbc710fada93b07a83fe95a67e00cb1fdbc80befda21f862d3fe3b8e715a2840abc797653a7d2f07b3fe93328926d9e92' +
    'bc8bb77003600cda3fe3eb25d36cd53abc5be570e1570fc03fe90b84784ddaf7bc70feb10ab93b873fe41d14e4ba67903c84608fd287ecf5' +
    '3fe8e37c303d9ad1bc6463a4b53d4bf83fe44eb381cf386bbc83ed6c1e6a55053fe8bb105a5dc9003c8863e03e9474c13fe48000e431159f' +
    'bc8b194a7463ed103fe89241985d871f3c8c48d9c413ed843fe4b0fc46aab7613c20da05738cc59a3fe869108d77a6c63c7338ffe2bfe9dd' +
    '3fe4e1a4e54ed51bbc8a492f89b7c76a3fe83f7dde701ca0bc4152cf609bc6e83fe511f9fd7b351cbc85c0e861c488313fe8158a31916d5d' +
    'bc6de8b90b8228de3fe541facddbb7243c7232c28520d3913fe7eb362eaa14883c5a1d65a4a5959f3fe571a6966d59b33c5c843b4d0fb198' +
    '3fe7c0827f09e54fbc6c73d6d72aee683fe5a0fc98813a12bc8d82e2b7d4227b3fe7956fcd7f6543bc8ab276e9d45ae43fe5cffc16bf8f0d' +
    '3c896cb370eb578a3fe769fec655211fbc6827d5cf8c68c53fe5fea4552a9e573c80b6cef7ee20b73fe73e30174efba1bc65d3ae3d94ad5f' +
    '3fe62cf49921ac79bc8edd9855b6241a3fe712046fa776783c8425b0a5029c813fe65aec2963e7553c8126f96b71053c3fe6e57c800cf55e' +
    '3c860286dedbd0a63fe6888a4e134b2fbc86b7d37644d5e63fe6b898fa9efb5d3c715ac786ccf4b23fe6b5ce50b7821abc65d5158f702e0f' +
    '3fe68b5a92eb6253bc89a91ad985f89c3fe6e2b77c40bde1bc70e729857fad533fe65dc1fdeb8cbabc597c1b47337c773fe70f451d0a8c40' +
    '3c697ede3885770d3fe62fcff20191c73c6d9143895756ef3fe73b7680dea578bc72248306dc12a23fe6018526f563df3c846ca5e0e432d0' +
    '3fe7674af6f7b5243c7e9d3f94ac84a83fe5d2e255f1f17a3c80314104c8892b3fe792c1d0041d52bc8abf05eeb354eb3fe5a3e839824077' +
    '3c8428aa2759be623fe7bdda5e28b3c23c4ad1197ccd03933fe574978d8e83f23c8f4714af282d233fe7e893f50379593c80eefbaa650c4c' +
    '3fe544f10f592ca5bc8e7ae8e6c7a62f3fe812ede9ae4ba4bc87830adf402dda3fe514f57d7bf3da3c747a108073c259' +
    ''
    const tab = new Float64Array(440)
    const dv = new DataView(new ArrayBuffer(8))
    for (let i = 0; i < 440; ++i)
    {
        dv.setUint32(0, parseInt(TAB_HEX.substr(16 * i, 8), 16))
        dv.setUint32(4, parseInt(TAB_HEX.substr(16 * i + 8, 8), 16))
        tab[i] = dv.getFloat64(0)
    }
    // usncs.h
    const s1 = -0x15555555555555 * Math.pow(2, -55), s2 = 0x11111111110ECE * Math.pow(2, -59), s3 = -0x1A01A019DB08B8 * Math.pow(2, -65)
    const s4 = 0x171DE27B9A7ED9 * Math.pow(2, -71), s5 = -0x1ADDFFC2FCDF59 * Math.pow(2, -78)
    const big = 0x18000000000000 * Math.pow(2, -7)
    const hp0 = 0x1921FB54442D18 * Math.pow(2, -52), hp1 = 0x11A62633145C07 * Math.pow(2, -106)
    const mp1 = 0x1921FB58000000 * Math.pow(2, -52), mp2 = -0x1DDE973C000000 * Math.pow(2, -79)
    const pp3 = -0x1CB3B398000000 * Math.pow(2, -107), pp4 = -0x1d747f23e32ed7 * Math.pow(2, -135)
    const hpinv = 0x145F306DC9C883 * Math.pow(2, -53), toint = 0x18000000000000 * Math.pow(2, 0)
    // s_sin.c
    const sn3 = -1.66666666666664880952546298448555E-01, sn5 = 8.33333214285722277379541354343671E-03
    const cs2 = 4.99999999999999999999950396842453E-01, cs4 = -4.16666666666664434524222570944589E-02
    const cs6 = 1.38888874007937613028114285595617E-03
    const f64 = new Float64Array(1), u32 = new Uint32Array(f64.buffer)   // little-endian host: u32[0] low, u32[1] high
    if (new Uint8Array(new Uint16Array([1]).buffer)[0] !== 1)
        throw new Error('glibc_sincos: little-endian host expected')
    const low = (x) => { f64[0] = x; return u32[0] }
    const highAbs = (x) => { f64[0] = x; return u32[1] & 0x7fffffff }
    const copysign = (a, b) => ((b < 0 || Object.is(b, -0)) !== (a < 0 || Object.is(a, -0))) ? -a : a

    function doCos(x, dx)
    {
        if (x < 0)
            dx = -dx
        const ux = big + Math.abs(x)
        x = Math.abs(x) - (ux - big) + dx
        const xx = x * x
        const s = x + x * xx * (sn3 + xx * sn5)
        const c = xx * (cs2 + xx * (cs4 + xx * cs6))
        const k = low(ux) << 2
        const sn = tab[k], ssn = tab[k + 1], cs = tab[k + 2], ccs = tab[k + 3]
        const cor = (ccs - s * ssn - cs * c) - sn * s
        return cs + cor
    }
    function doSin(x, dx)
    {
        const xold = x
        if (Math.abs(x) < 0.126)
        {
            const xx = x * x
            const t = (((((s5 * xx + s4) * xx + s3) * xx + s2) * xx + s1) * x - 0.5 * dx) * xx + dx
            return x + t
        }
        if (x <= 0)
            dx = -dx
        const ux = big + Math.abs(x)
        x = Math.abs(x) - (ux - big)
        const xx = x * x
        const s = x + (dx + x * xx * (sn3 + xx * sn5))
        const c = x * dx + xx * (cs2 + xx * (cs4 + xx * cs6))
        const k = low(ux) << 2
        const sn = tab[k], ssn = tab[k + 1], cs = tab[k + 2], ccs = tab[k + 3]
        const cor = (ssn + s * ccs - sn * c) + cs * s
        return copysign(sn + cor, xold)
    }
    // returns [n, a, da]
    function reduce(x)
    {
        const t = x * hpinv + toint
        const xn = t - toint
        const y = (x - xn * mp1) - xn * mp2
        const n = low(t) & 3
        let t1 = xn * pp3
        const t2 = y - t1
        let db = (y - t2) - t1
        t1 = xn * pp4
        const b = t2 - t1
        db += (t2 - b) - t1
        return [n, b, db]
    }
    function doSinCos(a, da, n)
    {
        const r = (n & 1) ? doCos(a, da) : doSin(a, da)
        return (n & 2) ? -r : r
    }
    function sin(x)
    {
        x = +x
        const k = highAbs(x)
        if (k < 0x3e500000)
            return x
        if (k < 0x3feb6000)
            return doSin(x, 0)
        if (k < 0x400368fd)
            return copysign(doCos(hp0 - Math.abs(x), hp1), x)
        if (k < 0x419921FB)
        {
            const r = reduce(x)
            return doSinCos(r[1], r[2], r[0])
        }
        if (k < 0x7ff00000)
            throw new Error('glibc_sincos: |x| >= 105414350 (__branred) not ported: ' + x)
        return x / x
    }
    function cos(x)
    {
        x = +x
        const k = highAbs(x)
        if (k < 0x3e400000)
            return 1.0
        if (k < 0x3feb6000)
            return doCos(x, 0)
        if (k < 0x400368fd)
        {
            const y = hp0 - Math.abs(x)
            const a = y + hp1
            const da = (y - a) + hp1
            return doSin(a, da)
        }
        if (k < 0x419921FB)
        {
            const r = reduce(x)
            return doSinCos(r[1], r[2], r[0] + 1)
        }
        if (k < 0x7ff00000)
            throw new Error('glibc_sincos: |x| >= 105414350 (__branred) not ported: ' + x)
        return x / x
    }
    return { sin, cos, tab, consts: { s1, s2, s3, s4, s5, big, hp0, hp1, mp1, mp2, pp3, pp4, hpinv, toint } }
})()
