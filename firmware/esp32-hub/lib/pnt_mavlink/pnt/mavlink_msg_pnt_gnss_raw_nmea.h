#pragma once
// MESSAGE PNT_GNSS_RAW_NMEA PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA 61006


typedef struct __mavlink_pnt_gnss_raw_nmea_t {
 uint64_t time_us; /*<  Hub monotonic time of the first byte.*/
 char sentence[96]; /*<  */
} mavlink_pnt_gnss_raw_nmea_t;

#define MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN 104
#define MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN 104
#define MAVLINK_MSG_ID_61006_LEN 104
#define MAVLINK_MSG_ID_61006_MIN_LEN 104

#define MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC 219
#define MAVLINK_MSG_ID_61006_CRC 219

#define MAVLINK_MSG_PNT_GNSS_RAW_NMEA_FIELD_SENTENCE_LEN 96

#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_GNSS_RAW_NMEA { \
    61006, \
    "PNT_GNSS_RAW_NMEA", \
    2, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_gnss_raw_nmea_t, time_us) }, \
         { "sentence", NULL, MAVLINK_TYPE_CHAR, 96, 8, offsetof(mavlink_pnt_gnss_raw_nmea_t, sentence) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_GNSS_RAW_NMEA { \
    "PNT_GNSS_RAW_NMEA", \
    2, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_gnss_raw_nmea_t, time_us) }, \
         { "sentence", NULL, MAVLINK_TYPE_CHAR, 96, 8, offsetof(mavlink_pnt_gnss_raw_nmea_t, sentence) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_gnss_raw_nmea message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time of the first byte.
 * @param sentence  
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, const char *sentence)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_char_array(buf, 8, sentence, 96);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#else
    mavlink_pnt_gnss_raw_nmea_t packet;
    packet.time_us = time_us;
    mav_array_memcpy(packet.sentence, sentence, sizeof(char)*96);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
}

/**
 * @brief Pack a pnt_gnss_raw_nmea message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time of the first byte.
 * @param sentence  
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, const char *sentence)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_char_array(buf, 8, sentence, 96);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#else
    mavlink_pnt_gnss_raw_nmea_t packet;
    packet.time_us = time_us;
    mav_array_memcpy(packet.sentence, sentence, sizeof(char)*96);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#endif
}

/**
 * @brief Pack a pnt_gnss_raw_nmea message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time of the first byte.
 * @param sentence  
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,const char *sentence)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_char_array(buf, 8, sentence, 96);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#else
    mavlink_pnt_gnss_raw_nmea_t packet;
    packet.time_us = time_us;
    mav_array_memcpy(packet.sentence, sentence, sizeof(char)*96);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
}

/**
 * @brief Encode a pnt_gnss_raw_nmea struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_gnss_raw_nmea C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_gnss_raw_nmea_t* pnt_gnss_raw_nmea)
{
    return mavlink_msg_pnt_gnss_raw_nmea_pack(system_id, component_id, msg, pnt_gnss_raw_nmea->time_us, pnt_gnss_raw_nmea->sentence);
}

/**
 * @brief Encode a pnt_gnss_raw_nmea struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_gnss_raw_nmea C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_gnss_raw_nmea_t* pnt_gnss_raw_nmea)
{
    return mavlink_msg_pnt_gnss_raw_nmea_pack_chan(system_id, component_id, chan, msg, pnt_gnss_raw_nmea->time_us, pnt_gnss_raw_nmea->sentence);
}

/**
 * @brief Encode a pnt_gnss_raw_nmea struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_gnss_raw_nmea C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_gnss_raw_nmea_t* pnt_gnss_raw_nmea)
{
    return mavlink_msg_pnt_gnss_raw_nmea_pack_status(system_id, component_id, _status, msg,  pnt_gnss_raw_nmea->time_us, pnt_gnss_raw_nmea->sentence);
}

/**
 * @brief Send a pnt_gnss_raw_nmea message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time of the first byte.
 * @param sentence  
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_gnss_raw_nmea_send(mavlink_channel_t chan, uint64_t time_us, const char *sentence)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_char_array(buf, 8, sentence, 96);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA, buf, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
#else
    mavlink_pnt_gnss_raw_nmea_t packet;
    packet.time_us = time_us;
    mav_array_memcpy(packet.sentence, sentence, sizeof(char)*96);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA, (const char *)&packet, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
#endif
}

/**
 * @brief Send a pnt_gnss_raw_nmea message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_gnss_raw_nmea_send_struct(mavlink_channel_t chan, const mavlink_pnt_gnss_raw_nmea_t* pnt_gnss_raw_nmea)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_gnss_raw_nmea_send(chan, pnt_gnss_raw_nmea->time_us, pnt_gnss_raw_nmea->sentence);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA, (const char *)pnt_gnss_raw_nmea, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_gnss_raw_nmea_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, const char *sentence)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_char_array(buf, 8, sentence, 96);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA, buf, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
#else
    mavlink_pnt_gnss_raw_nmea_t *packet = (mavlink_pnt_gnss_raw_nmea_t *)msgbuf;
    packet->time_us = time_us;
    mav_array_memcpy(packet->sentence, sentence, sizeof(char)*96);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA, (const char *)packet, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_MIN_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_GNSS_RAW_NMEA UNPACKING


/**
 * @brief Get field time_us from pnt_gnss_raw_nmea message
 *
 * @return  Hub monotonic time of the first byte.
 */
static inline uint64_t mavlink_msg_pnt_gnss_raw_nmea_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field sentence from pnt_gnss_raw_nmea message
 *
 * @return  
 */
static inline uint16_t mavlink_msg_pnt_gnss_raw_nmea_get_sentence(const mavlink_message_t* msg, char *sentence)
{
    return _MAV_RETURN_char_array(msg, sentence, 96,  8);
}

/**
 * @brief Decode a pnt_gnss_raw_nmea message into a struct
 *
 * @param msg The message to decode
 * @param pnt_gnss_raw_nmea C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_gnss_raw_nmea_decode(const mavlink_message_t* msg, mavlink_pnt_gnss_raw_nmea_t* pnt_gnss_raw_nmea)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_gnss_raw_nmea->time_us = mavlink_msg_pnt_gnss_raw_nmea_get_time_us(msg);
    mavlink_msg_pnt_gnss_raw_nmea_get_sentence(msg, pnt_gnss_raw_nmea->sentence);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN? msg->len : MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN;
        memset(pnt_gnss_raw_nmea, 0, MAVLINK_MSG_ID_PNT_GNSS_RAW_NMEA_LEN);
    memcpy(pnt_gnss_raw_nmea, _MAV_PAYLOAD(msg), len);
#endif
}
