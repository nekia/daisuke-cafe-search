const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const { OAuth2Client } = require('google-auth-library');
require('dotenv').config();

const app = express();
app.use(cors());

const mongodbConnStr = process.env.MONGODB_CONNECTION_STRING

console.log(`mongodbConnStr : ${mongodbConnStr}`);
console.log(`now : ${new Date().toString()}`);
mongoose.connect(mongodbConnStr, {
    useNewUrlParser: true,
    useUnifiedTopology: true
    // serverApi: { version: '1', strict: true, deprecationErrors: true }
}).then(() => {
    console.log('MongoDB connected successfully');
}).catch(err => {
    console.error('MongoDB connection error:', err);
});

const db = mongoose.connection.useDb('places');

const openingHourSchema = new mongoose.Schema({
    day: { type: Number, required: true },
    hour: { type: Number, required: true },
    minute: { type: Number, required: true },
    date: {
        day: { type: Number },
        month: { type: Number },
        year: { type: Number }
    },
    truncated: { type: Boolean }
});

const periodSchema = new mongoose.Schema({
    open: { type: openingHourSchema, required: true },
    close: { type: openingHourSchema, required: true }
});

const specialDaySchema = new mongoose.Schema({
    date: {
        day: { type: Number, required: true },
        month: { type: Number, required: true },
        year: { type: Number, required: true }
    }
});

const regularOpeningHoursSchema = new mongoose.Schema({
    openNow: { type: Boolean, required: true },
    nextCloseTime: { type: String },
    nextOpenTime: { type: String },
    periods: { type: [periodSchema], required: true },
    specialDays: { type: [specialDaySchema] },
    weekdayDescriptions: { type: [String], required: true }
});

const placeSchema = new mongoose.Schema({
    id: String,
    location_name: {
        text: String,
        languageCode: String
    },
    address: String,
    formattedAddress: String,
    alias: String,
    businessStatus: String,
    primary_type: {
        text: String,
        languageCode: String
    },
    /** Places API (New) の primaryType（例: cafe）。フィルタ・プリセットはこちらと primary_type.text の両方でマッチ */
    primary_type_api: { type: String, required: false },
    url: String,
    location: {
        latitude: Number,
        longitude: Number
    },
    openingHours: {
        type: regularOpeningHoursSchema,
        required: false,
        default: null
    },
    openingHoursStatus: String,
    category: Number,
    refreshMeta: {
        refreshBucket: Number,
        lastEnterpriseSyncAt: Date,
        businessStatusSyncedAt: Date,
        openingHoursSyncedAt: Date,
        nextEligibleAt: Date,
        lastEnterpriseStatus: String,
        lastProStatusSyncAt: Date,
        lastProStatus: String,
        placeIdInvalid: Boolean,
        placeIdInvalidAt: Date
    },
    enterpriseData: {
        latestSnapshot: mongoose.Schema.Types.Mixed,
        searchableTexts: [String]
    }
});

const Place = db.model('Place', placeSchema, 'place_info');

const client = new OAuth2Client(process.env.REACT_APP_GOOGLE_CLIENT_ID);

const verifyToken = async (req, res, next) => {
    const authHeader = req.headers['authorization'];
    if (!authHeader) {
        return res.status(401).send('Unauthorized');
    }
    const token = authHeader.split(' ')[1]; // Bearer プレフィックスを取り除く
    if (!token) {
        return res.status(401).send('Unauthorized');
    }
    try {
        const ticket = await client.verifyIdToken({
            idToken: token,
            audience: process.env.REACT_APP_GOOGLE_CLIENT_ID,
        });
        req.user = ticket.getPayload();
        next();
    } catch (error) {
        console.error(error);
        res.status(401).send('Unauthorized');
    }
};

const CLOSED_BUSINESS_STATUSES = ['CLOSED_PERMANENTLY', 'CLOSED_TEMPORARILY'];

const isClosedOnlyQuery = (value) => {
    if (Array.isArray(value)) {
        return value.some((item) => isClosedOnlyQuery(item));
    }
    if (typeof value !== 'string') {
        return false;
    }
    const normalized = value.trim().toLowerCase();
    return normalized === '1' || normalized === 'true' || normalized === 'yes';
};

app.get('/places', verifyToken, async (req, res) => {
    let query = {};
    const andConditions = [];
    let checkOpenDate = false;
    let specificDateTime = null;
    const closedOnly = isClosedOnlyQuery(req.query?.closedOnly);

    // 既定は営業中のみ。closedOnly=true なら閉業・臨時休業のみ
    query['businessStatus'] = closedOnly
        ? { $in: CLOSED_BUSINESS_STATUSES }
        : { $nin: CLOSED_BUSINESS_STATUSES };

    if (req.query) {
        const primary_type = req.query.primary_type;
        if (primary_type) {
            const typeList = Array.isArray(primary_type) && primary_type.length > 0
                ? primary_type
                : [primary_type];
            andConditions.push({
                $or: [
                { primary_type_api: { $in: typeList } },
                { 'primary_type.text': { $in: typeList } },
                ]
            });
            console.log('primary_type filter', typeList);
        }

        const category = req.query.category;
        const keyword = typeof req.query.q === 'string' ? req.query.q.trim() : '';
        if (category) {
            const rawList = Array.isArray(category) && category.length > 0
                ? category
                : [category];
            const normalized = rawList.flatMap((value) => {
                const asString = String(value);
                const asNumber = Number(value);
                return Number.isNaN(asNumber) ? [asString] : [asString, asNumber];
            });
            query['category'] = { $in: normalized };
            console.log(query.category)
        }

        // 閉業のみ表示時は「営業中」時刻フィルタは意味がないので無視
        if (req.query.dateTime && !closedOnly) {
            specificDateTime = new Date(req.query.dateTime);
            checkOpenDate = true;
        }

        if (keyword) {
            const tokens = keyword
                .split(/[\s\u3000]+/)
                .map((token) => token.trim())
                .filter(Boolean);

            // 検索対象: 店名 / primaryTypeDisplayName / generativeSummary / reviewSummary
            // 店名は「果実屋珈琲 調布…」とスペース無し入力の差を吸収するため \s* を挟む
            const tokenConditions = tokens.map((token) => {
                const safeRegex = new RegExp(escapeRegex(token), 'i');
                const flexibleNameRegex = new RegExp(
                    [...token].map((ch) => escapeRegex(ch)).join('\\s*'),
                    'i'
                );
                return {
                    $or: [
                        { 'location_name.text': flexibleNameRegex },
                        { alias: flexibleNameRegex },
                        { 'enterpriseData.latestSnapshot.displayName.text': flexibleNameRegex },
                        { 'enterpriseData.latestSnapshot.primaryTypeDisplayName.text': safeRegex },
                        { 'primary_type.text': safeRegex },
                        {
                            'enterpriseData.latestSnapshot.generativeSummary.description.text':
                                safeRegex,
                        },
                        // reviewSummary.text は LocalizedText（{ text, languageCode }）のことがある
                        { 'enterpriseData.latestSnapshot.reviewSummary.text': safeRegex },
                        { 'enterpriseData.latestSnapshot.reviewSummary.text.text': safeRegex },
                        { 'enterpriseData.searchableTexts': flexibleNameRegex },
                        { 'enterpriseData.searchableTexts': safeRegex },
                    ],
                };
            });

            if (tokenConditions.length > 0) {
                andConditions.push(...tokenConditions);
            }
            console.log('keyword search:', keyword);
        }
    }

    if (andConditions.length > 0) {
        query.$and = andConditions;
    }

    let places = await Place.find(query);

    // Add isOpenNow to each place
    places = places.map(place => {
        const isOpen = isOpenNow(place.openingHours, specificDateTime);
        if (!place.openingHours) {
            console.log("openingHours has not been assigned : " + place.location_name.text)
        }
        return { ...place.toObject(), isOpenNow: isOpen };
    });

    if (checkOpenDate) {
        places = places.filter(place => place.isOpenNow);
    }

    console.log("Length of places :" + places.length + (closedOnly ? ' (closedOnly)' : ''))
    res.json(places);
});

app.get('/primary_types', verifyToken, async (req, res) => {
    /** 表示は従来どおり primary_type.text の一意一覧（チェックボックスの value と一致させる） */
    const closedOnly = isClosedOnlyQuery(req.query?.closedOnly);
    const primaryTypes = await Place.distinct('primary_type.text', {
        businessStatus: closedOnly
            ? { $in: CLOSED_BUSINESS_STATUSES }
            : { $nin: CLOSED_BUSINESS_STATUSES },
    });
    console.log(primaryTypes.length, 'distinct primary_type.text', closedOnly ? '(closedOnly)' : '');
    res.json(primaryTypes);
});

app.listen(3001, () => {
    console.log('Server is running on port 3001');
});

const isOpenNow = (openingHours, specificDateTime) => {
    // openingHours が存在しない、null、または periods が存在しない場合は false を返す
    if (!openingHours || !openingHours.periods || !Array.isArray(openingHours.periods)) {
        return false;
    }

    const now = specificDateTime || new Date();
    const currentDay = now.getDay(); // 0: Sunday, 1: Monday, ..., 6: Saturday
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();
    
    // Check each period to see if the specified time falls within any open period
    for (const period of openingHours.periods) {
        // period の構造が正しいかチェック
        if (period && period.open && period.close && 
            period.open.day === currentDay &&
            typeof period.open.hour === 'number' && 
            typeof period.open.minute === 'number' &&
            typeof period.close.hour === 'number' && 
            typeof period.close.minute === 'number') {
            
            const openTime = period.open.hour * 60 + period.open.minute;
            const closeTime = period.close.hour * 60 + period.close.minute;
            const currentTime = currentHour * 60 + currentMinute;
            
            if (currentTime >= openTime && currentTime < closeTime) {
                return true;
            }
        }
    }
    return false;
};

const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');