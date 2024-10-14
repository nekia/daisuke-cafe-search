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
    primary_type: String, // 修正: genre -> primary_type
    url: String,
    location: {
        latitude: Number,
        longitude: Number
    }
});

const Place = mongoose.model('Place', placeSchema, 'place_info');

app.get('/places', async (req, res) => {
    const { primary_type } = req.query; // 修正: genre -> primary_type
    let query = {};

    if (primary_type) {
        query.primary_type = primary_type;
    }

    let places = await Place.find(query);
    console.log(places)
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

app.listen(3001, () => {
    console.log('Server is running on port 3001');
});