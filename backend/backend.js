const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');

const app = express();
app.use(cors());

mongoose.connect('mongodb://localhost:27017/places', { useNewUrlParser: true, useUnifiedTopology: true });

const placeSchema = new mongoose.Schema({
    id: String,
    location_name: {
        text: String,
        languageCode: String
    },
    address: String,
    primary_type: {
        text: String,
        languageCode: String
    },
    url: String,
    location: {
        latitude: Number,
        longitude: Number
    }
});

const Place = mongoose.model('Place', placeSchema, 'place_info');

app.get('/places', async (req, res) => {
    let query = {};

    if (req.query) {
        const primary_type = req.query.primary_type;
        if (primary_type){
            if (Array.isArray(primary_type) && primary_type.length > 0) {
                query['primary_type.text'] = { $in: primary_type };
            } else if(!Array.isArray(primary_type)) {
                query['primary_type.text'] = { $in: [primary_type] };
            }
            console.log(query['primary_type.text'])
        }
    }

    let places = await Place.find(query);
    console.log("Length of places :" + places.length)
    // places = [
    //     {
    //         name: "abc",
    //         id: "ChIJUaH7BAKNGGARyFZObTEQXj4",
    //         latitude: 35.6710614,
    //         longitude: 139.7075722,
    //         url: "https://maps.google.com/?cid=4494047282635626184"
    //     }
    // ];
    res.json(places);
});

app.get('/primary_types', async (req, res) => {
    const primaryTypes = await Place.distinct('primary_type.text');
    console.log(primaryTypes)
    res.json(primaryTypes);
});

app.listen(3001, () => {
    console.log('Server is running on port 3001');
});