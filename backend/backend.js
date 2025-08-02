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
    alias: String,
    businessStatus: String,
    primary_type: {
        text: String,
        languageCode: String
    },
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
    category: Number
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

app.get('/places', verifyToken, async (req, res) => {
    let query = {};
    let checkOpenDate = false;
    let specificDateTime = null;

    // CLOSED_PERMANENTLYのレコードを除外
    query['businessStatus'] = { $ne: 'CLOSED_PERMANENTLY' };

    if (req.query) {
        const primary_type = req.query.primary_type;
        if (primary_type) {
            if (Array.isArray(primary_type) && primary_type.length > 0) {
                query['primary_type.text'] = { $in: primary_type };
            } else if (!Array.isArray(primary_type)) {
                query['primary_type.text'] = { $in: [primary_type] };
            }
            console.log(query['primary_type.text'])
        }

        const category = req.query.category;
        if (category) {
            if (Array.isArray(category) && category.length > 0) {
                query['category'] = { $in: category };
            } else if (!Array.isArray(category)) {
                query['category'] = { $in: [category] };
            }
            console.log(query.category)
        }

        if (req.query.dateTime) {
            specificDateTime = new Date(req.query.dateTime);
            checkOpenDate = true;
        }
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

    console.log("Length of places :" + places.length)
    res.json(places);
});

app.get('/primary_types', verifyToken, async (req, res) => {
    const primaryTypes = await Place.distinct('primary_type.text', { businessStatus: { $ne: 'CLOSED_PERMANENTLY' } });
    console.log(primaryTypes)
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